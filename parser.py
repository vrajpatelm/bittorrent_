import hashlib


def bdncode_to_dict(info_file):
    def parse_str(data1, item=0):
        colon = data1.index(b":", item)
        len_str = int(data1[item:colon])
        start = colon + 1
        struc_str = data1[start:start + len_str]
        return struc_str, len_str + start

    def parse_int(data, item=0):
        end = data.index(b"e", item)
        formated_int = int(data[item + 1:end])
        return formated_int, end + 1

    def parse_dict(data, item=0):
        dict1 = {}
        item = item + 1
        while item < len(data) and data[item] != ord("e"):
            val, item = parse_any(data, item)
            val1, item = parse_any(data, item)
            dict1[val] = val1
        return dict1, item + 1

    def parse_list(data, item=0):
        list1 = []
        item = item + 1
        while item < len(data) and data[item] != ord("e"):
            # print("item: ", data[item],item)
            val, item = parse_any(data, item)
            list1.append(val)
        # print(list1)
        return list1, item + 1

    def parse_any(data, i=0):
        if data[i] == ord("i"):
            return parse_int(data, i)
        elif data[i] == ord("d"):
            return parse_dict(data, i)
        elif data[i] == ord("l"):
            return parse_list(data, i)
        elif ord('0') <= data[i] <= ord('9'):
            return parse_str(data, i)
        else:
            raise ValueError(f"Invalid input {data[i]}")

    return parse_any(info_file, 0)[0]


"""
 It convert now dictionary to BDencode formate
"""


def dict_to_bdncode_dict_(data1):
    str1 = b""
    for i in data1.items():
        str1 = str1 + str_to_bencode(i[0])
        str1 = str1 + find_parse(i[1])
    return b"d" + str1 + b"e"


def str_to_bencode(value):
    return b"" + str(len(value)).encode() + b":" + value


def byte_to_bencode(value):
    return b"i" + str(value).encode() + b"e"


def find_parse(value):
    if type(value) == str:
        return str_to_bencode(value.encode())
    elif type(value) == bytes:
        return str_to_bencode(value)
    elif type(value) == int:
        return byte_to_bencode(value)
    elif type(value) == list:
        ls1 = b"l"
        for i in range(len(value)):
            ls1 += find_parse(value[i])
        return ls1 + b"e"
    elif type(value) == dict:
        return dict_to_bdncode_dict_(value)
    else:
        raise ValueError(f"Invalid input {value}")




def decode_peers(resp_data):
    return None