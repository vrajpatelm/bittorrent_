import asyncio
import socket
import struct
import hashlib
import time
import TrackerRequest
from collections import defaultdict

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
        pstr = b"Bittorrent protocol"
        reserved_byte = b"\x00"*8
        bittorrent_shake = bytes(len(pstr))+pstr + reserved_byte+ self.info_hash + self.peer_id
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
            if res_pstrln !=19 and res_pstr != pstr:
                print(f"Invalid handShake from {self.ip} and {self.port}")
            if res_info_hash!=self.info_hash:
                print(f"Invalid info_hash from {self.ip} and {self.port}")
            print(f"✓ Handshake successful with {self.ip}:{self.port}")
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
            print(f"✓ {self.ip}:{self.port} unchoked us")
        elif msg_id==2:
            self.peer_interested=True
        elif msg_id == 3:
            self.peer_interested = True
        elif msg_id == 4:
            self.peer_interested = False
        elif msg_id == 5:
            piece_index = struct.unpack(">I", payload)[0]
        elif msg_id==6:
            self.bitfield = payload
            print(f"✓ Received bitfield from {self.ip}:{self.port}")
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
    async def download_piece_from_peers(self,peer,piece_index,piece_length,block_size=16384): # block size 16KB
        """
            Download a single piece from a peer.
            Returns dict of {offset: block_data} or None if failed.
        """
        if not peer.has_peice():
            return None
        if not peer.interested:
            await peer.send_interested()

        # waite for unchoke msg
        wait_time =0
        if peer.choked and wait_time >5:
            msg,payload = peer.receive_message()
            print(msg,payload)

from TrackerRequest import get_peers_from_tracker
if __name__ == "__main__":
    peers = TrackerRequest.get_peers_from_tracker("C:\\Users\VRAJ\Downloads\\test.torrent")
    bitt = BittorrentPeer("151.59.115.17", 48909 ,b"\xd9\x84\xf6z\xf9\x91{!L\xd8\xb6\x04\x8a\xb5bL}\xf6\xa0z","-PC0001-ItDonueIMvfW")

    print(bitt.bitfield)