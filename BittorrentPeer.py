import asyncio
import os
import socket
import struct
import hashlib
from parser import bdncode_to_dict,dict_to_bdncode_dict_

class BittorrentPeer:
    """Handel single peer communication"""
    def __init__(self,ip,port,info_hash,peer_id,timeout=10):
        self.writer = None
        self.reader = None
        self.socket=None
        self.info_hash=info_hash
        self.ip=ip
        self.peer_id=peer_id
        self.port =port
        self.timeout = timeout
        self.peer_choking = True
        self.peer_interested = False
        self.choked = False
        self.interested= False
        self.bitfield= None

    async def connect(self):
        #? Established TCP Connection to peer.
       try:
           self.reader , self.writer = await asyncio.wait_for(asyncio.open_connection(self.ip,self.port),
                                                        timeout=self.timeout)
           return True
       except Exception as e:
           print(f"The exception happened {e} for ip = {self.ip} and port= {self.port } ")
           return False

    async def handshake(self):
        #! Peer hand-Shake
        pstr = b"BitTorrent protocol"
        reserved_byte = b"\x00\x00\x00\x00\x00\x00\x00\x00"
        bittorrent_shake = struct.pack("B", len(pstr)) + pstr + reserved_byte + self.info_hash + self.peer_id
        try:
            self.writer.write(bittorrent_shake)
            await self.writer.drain() # flush the write buffer
            # receive handShake
            response =await asyncio.wait_for( self.reader.readexactly(68) , timeout= self.timeout)
            # parse response

            res_pstrln = response[0]
            res_pstr = response[1:20] # 19bytes
            res_info_hash = response[28:48]

            #verify the response
            if res_pstrln !=19 or res_pstr != pstr:
                print(f"Invalid handShake from {self.ip} and {self.port}")
            if res_info_hash!=self.info_hash:
                print(f"Invalid info_hash from {self.ip} and {self.port}")
            print(f"[OK] Handshake successful with {self.ip}:{self.port}")
            return True
        except Exception as e:
            print(f"The exception happened {e} for ip = {self.ip} and port= {self.port} ")
            return False

    async def send_interested(self):
        """Send 'interested' message to peer."""
        msg = struct.pack(">IB",1,2)# Format <len of prefix><msg ID>
        self.writer.write(msg)
        await self.writer.drain()
        self.interested=True
    async def send_request(self,piece_index,begin,length):
        """ Request Block from peers"""
        req_msg = struct.pack(">IBIII",13,6,piece_index,begin,length)
        self.writer.write(req_msg)
        await self.writer.drain()

    async def receive_message(self):
        """Receive and parse a message from peer."""
        try:
            length_data= await asyncio.wait_for(self.reader.readexactly(4),timeout=self.timeout)
            length = struct.unpack(">I",length_data)[0]

            if length==0:
                return None,None
            # read msg+playload
            msg_data = await asyncio.wait_for(self.reader.readexactly(length), timeout=self.timeout)

            msg_id = msg_data[0]
            payload = msg_data[1:] if length>1 else b""

            return msg_id , payload
        except asyncio.TimeoutError:
            return None, None
        except Exception as e:
            return None, None

    async def handel_message(self,msg_id,payload):
        if msg_id ==None:
            return None

        if msg_id==0:
            self.peer_choking = True
        elif msg_id==1:
            self.peer_choking= False
            print(f"[OK] {self.ip}:{self.port} unchoked us")
        elif msg_id==2:
            self.peer_interested=True
        elif msg_id == 3:
            self.peer_interested = False
        elif msg_id == 4:
            piece_index = struct.unpack(">I", payload)[0]
            if self.bitfield is not None:
                byte_index = piece_index // 8
                bit_index = 7 - (piece_index % 8)
                if byte_index < len(self.bitfield):
                    temp = bytearray(self.bitfield)
                    temp[byte_index] |= (1 << bit_index)
                    self.bitfield = bytes(temp)
        elif msg_id == 5:
            self.bitfield = payload
            print(f"[OK] Received bitfield from {self.ip}:{self.port}")
        elif msg_id == 7:
            index = struct.unpack(">I", payload[0:4])[0]
            begin = struct.unpack(">I", payload[4:8])[0]
            block = payload[8:]

            return ('piece', index, begin, block)
        return None
    async def has_piece(self, index):
        if self.bitfield is None:
            return False
        byte_index = index//8
        bit_index = 7-(index%8)
        if byte_index >= len(self.bitfield):
            return False
        return bool((self.bitfield[byte_index]>> bit_index) & 1)

    async def close(self):
        """Close connection to peers"""
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
        self.connected = False
    async def download_piece_from_peers(self,piece_index,piece_length,block_size=16384): # block size 16KB
        """
            Download a single piece from a peer.
            Returns dict of {offset: block_data} or None if failed.
        """
        if not  await self.has_piece(piece_index):
            return None
        if not self.interested:
            await self.send_interested()

        # wait for unchoke msg
        wait_time =0
        while self.peer_choking and wait_time <5:
            msg_id,payload = await self.receive_message()
            if msg_id is not None:
                await self.handel_message(msg_id,payload)
            await asyncio.sleep(0.1)
            wait_time+=0.1

        if self.peer_choking :
            return None
        
        #Request all the block of the peice
        blocks_needed=[]
        for begin in range(0,piece_length,block_size):
            length = min(block_size,piece_length-begin)
            blocks_needed.append((begin,length))
            await self.send_request(piece_index,begin,length)
        # collect blocks
        
        piece_data={}
        timeout_counter=0
        max_timeout=100
        while len(piece_data)<len(blocks_needed) and timeout_counter<max_timeout:
            msg_id,payload = await self.receive_message()
            
            if msg_id is None:
                timeout_counter+=1
                await asyncio.sleep(0.1)
                continue
            result = await self.handel_message(msg_id,payload)
            if result and result[0]=="piece":
                _,idx,begin,block=result
                if idx==piece_index:
                    piece_data[begin]=block
                    timeout_counter=0
        if len(piece_data)<len(blocks_needed):
            return None
        
        return piece_data
class TorrentDownloader:
    """Manage concurrent downloading from multiple peers."""
    def __init__(self,torrent_file_path,peers,max_peers=5):
        # max_peer = 5 because to prevent too many open connection for performance
        self.torrent_file_path=torrent_file_path
        self.peers =peers
        self.max_peers = max_peers
        
        with open(torrent_file_path,"rb") as f:
            torrent_data = bdncode_to_dict(f.read())

        print(torrent_data)
        self.info = torrent_data[b"info"]
        self.info_hash = hashlib.sha1(dict_to_bdncode_dict_(self.info)).digest()
        self.piece_length = self.info[b'piece length']
        self.pieces_hash = self.info[b'pieces']
        self.num_pieces = len(self.pieces_hash)//20
        
        # calculate Total length of all the files if availabe
        if b"length" in self.info:
            # for single line
            self.total_len = self.info[b"length"]
        else:
            # for multiple files
            self.total_len = sum(f[b"length"] for f in self.info[b"files"])
        self.peer_id = b"-PY0001-"+os.urandom(12) # peerid: 20byte "-<client id><version>-"+<remaing 12byte>

        #peice management
        self.downloaded_pieces = {}
        self.piece_locks = {i: asyncio.Lock() for i in range(self.num_pieces)} # each peice has one peer at a time
        self.pieces_in_progress = set()
        self.connected_peers = []

        print(f"Torrent: {self.num_pieces} pieces, {self.total_len} bytes total")
            
    def get_peice_length(self,piece_idx):
        """Get the length of a specific piece."""
        if piece_idx==self.num_pieces-1: # check for last peice which is mostly smaller than rest
            return self.total_len -(piece_idx *self.piece_length)
        return self.piece_length
    def get_piece_hash(self,piece_idx):
        """Get the hash of a specific piece."""
        return self.pieces_hash[piece_idx*20:(piece_idx +1)*20]

    def verify_piece(self,piece_idx,piece_data):
        calculate_hash = hashlib.sha1(piece_data).digest()
        expected_hash=self.get_piece_hash(piece_idx)
        return calculate_hash==expected_hash

    async def peer_worker(self, ip, port):
        peer =BittorrentPeer(ip,port,self.info_hash,self.peer_id)

        if not await peer.connect():
            return
        if not await peer.handshake():
            await peer.close()
            return

        # wait for bit field
        for _ in range(50):
            msg_id ,payload = await peer.receive_message()
            if msg_id is not None:
               await peer.handel_message(msg_id, payload)
            if peer.bitfield is not None:
                break
            await asyncio.sleep(0.1)

        self.connected_peers.append(peer)

        try:
            # download peice
            while len(self.downloaded_pieces) < self.num_pieces :
                # find a peice to download
                piece_idx =None
                for i in range(self.num_pieces):
                    if i not in self.pieces_in_progress and i not in self.downloaded_pieces and await peer.has_piece(i):
                         async with self.piece_locks[i]:
                             if i not in self.pieces_in_progress:
                                self.pieces_in_progress.add(i)
                                piece_idx=i
                                break
                if piece_idx is None:
                    # No pieces available, wait a bit
                    await asyncio.sleep(1)
                    continue
                piece_len = self.get_peice_length(piece_idx)
                piece_block =await peer.download_piece_from_peers(piece_idx,piece_len)

                if piece_block:
                    #The Piece is downloaded
                    #Assemble the peice
                    complete_piece = b''+b''.join(
    piece_block[offset] for offset in sorted(piece_block.keys())
)

                    #verify
                    if self.verify_piece(piece_idx,complete_piece):
                        async  with self.piece_locks[piece_idx]:
                            self.downloaded_pieces[piece_idx]=complete_piece
                            self.pieces_in_progress.discard(piece_idx)

                    progress =len(self.downloaded_pieces)
                    print(f"[OK] Piece {piece_idx} downloaded from {ip}:{port} ({progress}/{self.num_pieces})")

                else:
                    #failed download
                    async with self.piece_locks[piece_idx]:
                        self.pieces_in_progress.discard(piece_idx)
                    await asyncio.sleep(0.5)
        except Exception as e:
            print(f"Error in peer worker {ip}:{port}: {e}")
        finally:
            await peer.close()
            if peer in self.connected_peers:
                self.connected_peers.remove(peer)

    async def download(self ,output_file):
        """Start a concurrent Download from multiple peers"""

        # create worker task for peers
        tasks=[]
        for ip , port in self.peers[:self.max_peers*2]:
            task = asyncio.create_task(self.peer_worker(ip,port))
            tasks.append(task)
            await  asyncio.sleep(0.1)#stagger connection

            # wait for completion of all the task
        while len(self.downloaded_pieces)< self.num_pieces and any(not t.done() for t in tasks):
            await asyncio.sleep(1)
            print(f"Progress: {len(self.downloaded_pieces)}/{self.num_pieces} pieces, "
                      f"{len(self.connected_peers)} peers connected")
            #cancel reaming task:
        for task in tasks:
            if not task.done():
                task.cancel()

        await  asyncio.gather(*tasks,return_exceptions=True)

        # Write to file if complete
        if len(self.downloaded_pieces) == self.num_pieces:
            print("Download Completed!!")
            with open (output_file,'wb') as f:
                for i in range(self.num_pieces):
                    f.write(self.downloaded_pieces[i])
            return True
        else:
                print(f"\n[FAILED] Download incomplete: {len(self.downloaded_pieces)}/{self.num_pieces} pieces")
                return False
    async def download_from_peers_async(self,torrent_file,peers,output_file,max_peers=5):
        """
            Download a torrent using multiple peers concurrently.

            Args:
                torrent_file: Path to .torrent file
                peers: List of (ip, port) tuples
                output_file: Path to save downloaded file
                max_peers: Maximum number of concurrent peer connections
        """
        downloader = TorrentDownloader(torrent_file,peers,max_peers)
        flag = await downloader.download(output_file)
        return flag

from TrackerRequest import get_peers_from_tracker
if __name__ == "__main__":
    async def main():
        torrent_path = "alicesadventures19033gut_archive.torrent"
        if not os.path.exists(torrent_path):
            # Check parent directory too
            torrent_path = os.path.join("..", torrent_path)
        peers = get_peers_from_tracker(torrent_path)
        print(f"Found peers from tracker: {peers}")
        t = TorrentDownloader(torrent_path, peers)
        success = await t.download_from_peers_async(
            torrent_path,
            peers,
            'downloaded_file.bin',
            max_peers=50
        )

        if success:
            print("Download successful!")
        else:
            print("Download failed or incomplete")

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nDownload interrupted by user")

    