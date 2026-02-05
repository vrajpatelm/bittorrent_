import random
import string
import parser
import hashlib

import urllib.parse
import urllib.request

def get_peers_from_tracker(torrent_file_path,port=6881,numwant=50):
    """
    Build a url to send tracker request for the list of peers
    :param numwant:
    :param port:
    :param torrent_file_path:
    :return: None
    """
    with open(torrent_file_path, 'rb') as f:
        torrent_data = f.read()
    decode = parser.bdncode_to_dict(torrent_data)

    if b"announce" not in decode:
        raise ValueError("No announce value found in torrent_file_path")
    announce = decode[b"announce"].decode('utf-8')

    # Info hash calculate
    try:
        info = decode[b"info"]
        info_bencoded = parser.dict_to_bdncode_dict_(info)
        info_hash = hashlib.sha1(info_bencoded).digest()
    except KeyError:
        raise ValueError("No ""info"" value found in torrent_file_path")
    # print(info_hash)
    # print("Announace ",announce)
    # print(decode[b"info"][b"files"])

    # generate peer_id
    prefix = "-PC0001-" # my cilent + version
    suffix = "".join(random.choices(string.ascii_letters+string.digits,k=12))
    peer_id = prefix+suffix

    # Byte left to

    if b"length" in info:
        bytes_left = info[b"length"]
    elif b"files"in info:
        bytes_left = sum(i[b"length"] for i in info[b"files"])
    else:
        raise ValueError("No length or files found in torrent_file_path")
    params={
        "info_hash":info_hash,
        "peer_id":peer_id,
        "port":port,
        "uploaded":0,
        "downloaded":0,
        "left":bytes_left,
        "compact":1,
        "event":"started",
        "numwant":numwant,
        }
    #build url for request
    # encode the url properly
    queue_parts=[]
    for key ,val in params.items():
        if isinstance(val,bytes):

            encode_val = urllib.parse.quote(val,safe='')
            queue_parts.append(f"{key}={encode_val}")
        else:
            queue_parts.append(f"{key}={urllib.parse.quote(str(val),safe='')}")

    query_string = "&".join(queue_parts) # and+parts+and symbol
    # build full announcement string
    if "?"in announce:
        full_url = announce + "&"+query_string
    else:
        full_url = announce + "?"+query_string

        #send http request
    with urllib.request.urlopen(full_url,timeout=10) as response:
        tracker_data = response.read()
    tracker_decoded_data = parser.bdncode_to_dict(tracker_data)

    if b"failure reason" in tracker_decoded_data:
        failure = tracker_decoded_data[b"failure reason"].decode("utf-8")
        raise ValueError(f"The Error is {failure}")
    if b"peers" not in tracker_decoded_data:
        raise ValueError("Peers is not present")
    peers_data = tracker_decoded_data[b'peers']

    # to make peers_ip_list for both compact and non-compact ip

    # for Compact 4byes (ip address)+ 2bytes(port)
    peers=[]
    if isinstance(peers_data,bytes):
        if len(peers_data)%6!=0:
            raise ValueError("Invaild Compact peer_data")
        #! For non_compact is left

    elif isinstance(peers_data,list):
        for peer in peers_data:
            ip = peer[b"ip"].decode("utf-8")
            port = peer[b"port"]
            peers.append((ip,port))
    else:
        raise ValueError("Unknown peers data ")

    return peers


get_peers_from_tracker("C:\\Users\VRAJ\Downloads\\test.torrent")