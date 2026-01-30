import sys
import os
import bencodepy

# def read_torrent_file(torrent_file):
# def encode_to_bencode(data):

def parse_str(data1,item=0):
    colon = data1.index(":", item)
    len_str = int(data1[item:colon])
    spec_char = data1.index(":")
    struc_str = data1[spec_char+1:len_str+3]
    return struc_str , len_str+2+item

def parse_int(data="i2900e",item=0):
    end = data.index("e",item)
    formated_int = int(data[item+1:end])
    return formated_int , end+1+item


def parse_dict(data, item=0):
    start = data.index("d",item)
    end = data.index("e",item)
    dict1={}
    item = start + 1
    while item < end:
        val , item = parse_any(data, item)
        val1 ,item = parse_any(data, item)
        dict1[val] = val1
    return dict1 , item


def parse_list(data="l4:vraji-20ee",item=0):
    start = data.index("l")
    end = data.rfind("e")
    list1 = []
    item = start+1
    while item < end :
        print("item: ", data[item],item)
        val , item = parse_any(data, item)
        list1.append(val)
        print(list1)
    return list1 , item

def parse_any(data , i):
    if data[i] == "i":
        return parse_int(data,i)
    elif data[i] == "d":
        return parse_dict(data,i)
    elif data[i] == "l":
        return parse_list(data,i)
    elif data[i].isdigit():
        return parse_str(data,i)
    else:
        raise ValueError(f"Invalid input {data[i]}")




print(parse_list(data="l4:vraji-20ee"))
# Press the green button in the gutter to run the script.
# EBencoding = "d4:name5:Alice3:ageli20ee"
# parse_int(data="i29e")
# parse_str('10:spam')
# encode_to_bencode("C:\\Users\VRAJ\Downloads\PG hostel.txt.torrent")




