import sys
import os
import bencodepy

# def read_torrent_file(torrent_file):
# def encode_to_bencode(data):
def encode_to_bencode(info_file):
    def parse_str(data1,item=0):
        colon = data1.index(b":", item)
        len_str = int(data1[item:colon])
        start = colon+1
        struc_str = data1[start:start+len_str]
        return struc_str , len_str+start

    def parse_int(data,item=0):
        end = data.index(b"e",item)
        formated_int = int(data[item+1:end])
        return formated_int , end+1


    def parse_dict(data, item=0):
        dict1={}
        item = item + 1
        while item < len(data) and data[item] !=ord("e"):
            val , item = parse_any(data, item)
            val1 ,item = parse_any(data, item)
            dict1[val] = val1
        return dict1 , item+1


    def parse_list(data,item=0):
        list1 = []
        item = item+1
        while item < len(data) and data[item] !=ord("e") :
           # print("item: ", data[item],item)
            val , item = parse_any(data, item)
            list1.append(val)
           # print(list1)
        return list1 , item+1

    def parse_any(data , i=0):
        if data[i] == ord("i"):
            return parse_int(data,i)
        elif data[i] == ord("d"):
            return parse_dict(data,i)
        elif data[i] == ord("l"):
            return parse_list(data,i)
        elif ord('0') <= data[i] <= ord('9'):
            return parse_str(data,i)
        else:
            raise ValueError(f"Invalid input {data[i]}")

    with open(info_file,"rb") as f:
        return parse_any(f.read(),0)[0]






print(encode_to_bencode("C:\\Users\VRAJ\Downloads\PG hostel.txt.torrent")[b"info"])




