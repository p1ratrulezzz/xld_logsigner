#!/usr/bin/python

import sys
import copy
import struct
import argparse


LOGCHECKER_MIN_VERSION = '20121027'
MAGIC_CONSTANTS = [0x99036946, 0xe99db8e7, 0xe3ae2fa7, 0xa339740, 0xf06eb6a9, 0x92ff9b65, 0x28f7873, 0x9070e316]
MAGIC_INITIAL_STATE = 0x48853afc6479b873
DIGEST_LENGTH = 64 + len('\nVersion=0001')


def bit_concat32(high, low):
    return ((high & 0xFFFFFFFF) << 32) | (low & 0xFFFFFFFF)

def byte_swap(bits, n):
    n = n & (1 << bits) - 1
    return int.from_bytes(n.to_bytes(bits // 8, 'little')[::-1], 'little')

def LODWORD(n):
    return n & 0x00000000FFFFFFFF

def HIDWORD(n):
    return (n & 0xFFFFFFFF00000000) >> 32

def set_LODWORD(n, v):
    return (n & 0xFFFFFFFF00000000) | (v & 0xFFFFFFFF)

def set_HIDWORD(n, v):
    return (n & 0x00000000FFFFFFFF) | ((v & 0xFFFFFFFF) << 32)

def rotate_left(n, k):
    return ((n << k) & 0xFFFFFFFF) | (n >> (32 - k))

def rotate_right(n, k):
    return ((n >> k) | (n << (32 - k))) & 0xFFFFFFFF


def almost_sha256(data):
    # Non-standard initial state
    state = (0x1D95E3A4, 0x06520EF5, 0x3A9CFB75, 0x6104BCAE, 0x09CEDA82, 0xBA55E60B, 0xEAEC16C6, 0xEB19AF15)

    # Standard round constants
    round_constants = (0x428A2F98, 0x71374491, 0xB5C0FBCF, 0xE9B5DBA5, 0x3956C25B, 0x59F111F1, 0x923F82A4, 0xAB1C5ED5, 0xD807AA98, 0x12835B01, 0x243185BE, 0x550C7DC3, 0x72BE5D74, 0x80DEB1FE, 0x9BDC06A7, 0xC19BF174, 0xE49B69C1, 0xEFBE4786, 0x0FC19DC6, 0x240CA1CC, 0x2DE92C6F, 0x4A7484AA, 0x5CB0A9DC, 0x76F988DA, 0x983E5152, 0xA831C66D, 0xB00327C8, 0xBF597FC7, 0xC6E00BF3, 0xD5A79147, 0x06CA6351, 0x14292967, 0x27B70A85, 0x2E1B2138, 0x4D2C6DFC, 0x53380D13, 0x650A7354, 0x766A0ABB, 0x81C2C92E, 0x92722C85, 0xA2BFE8A1, 0xA81A664B, 0xC24B8B70, 0xC76C51A3, 0xD192E819, 0xD6990624, 0xF40E3585, 0x106AA070, 0x19A4C116, 0x1E376C08, 0x2748774C, 0x34B0BCB5, 0x391C0CB3, 0x4ED8AA4A, 0x5B9CCA4F, 0x682E6FF3, 0x748F82EE, 0x78A5636F, 0x84C87814, 0x8CC70208, 0x90BEFFFA, 0xA4506CEB, 0xBEF9A3F7, 0xC67178F2)

    # Pad the data with a single 1 bit, enough zeroes, and the original message bit length
    L = 8 * len(data)
    K = next(i for i in range(0, 512) if (L + 1 + i + 64) % 512 == 0)

    data += b'\x80' + (b'\x00' * ((K - 7) // 8)) + L.to_bytes(8, 'big')

    for start in range(0, len(data), 64):
        chunk = data[start:start + 64]

        round_state = [0] * 64
        round_state[0:16] = struct.unpack('!16L', chunk)
        
        for i in range(16, 64):
            s0 = rotate_right(round_state[i - 15], 7) ^ rotate_right(round_state[i - 15], 18) ^ (round_state[i - 15] >> 3)
            s1 = rotate_right(round_state[i - 2], 17) ^ rotate_right(round_state[i - 2], 19) ^ (round_state[i - 2] >> 10)

            round_state[i] = (round_state[i - 16] + s0 + round_state[i - 7] + s1) & 0xFFFFFFFF
        
        a, b, c, d, e, f, g, h = state
        
        for i in range(64):
            s0 = rotate_right(a, 2) ^ rotate_right(a, 13) ^ rotate_right(a, 22)
            maj = (a & b) ^ (a & c) ^ (b & c)
            t2 = s0 + maj

            s1 = rotate_right(e, 6) ^ rotate_right(e, 11) ^ rotate_right(e, 25)
            ch = (e & f) ^ ((~e) & g)
            t1 = h + s1 + ch + round_constants[i] + round_state[i]
            
            h = g
            g = f
            f = e
            e = (d + t1) & 0xFFFFFFFF
            d = c
            c = b
            b = a
            a = (t1 + t2) & 0xFFFFFFFF

        state = [(x + y) & 0xFFFFFFFF for x, y in zip(state, [a, b, c, d, e, f, g, h])]

    return b''.join([i.to_bytes(4, 'big') for i in state[:8]]).hex()


def scramble(data):
    previous = MAGIC_INITIAL_STATE
    mod_current = 0

    output = b''

    for size in range(DIGEST_LENGTH, 0, -8):
        current = 0

        needs_padding = (size < 8)  # We will always need padding in the end

        if not needs_padding:
            offset = DIGEST_LENGTH - size
            chunk1 = int.from_bytes(data[offset:offset + 4], 'little')
            chunk2 = int.from_bytes(data[offset + 4:offset + 8], 'little')

            current = previous ^ bit_concat32(byte_swap(32, chunk2), byte_swap(32, chunk1))
        else:
            current = byte_swap(64, bit_concat32(mod_current, HIDWORD(mod_current)))

        for i in range(4):
            for j in range(2):
                current = set_HIDWORD(current, HIDWORD(current) ^ current)

                a = (MAGIC_CONSTANTS[4*j + 0] + HIDWORD(current)) & 0xFFFFFFFF
                b = a
                a = rotate_left(a, 1)
                c = (b - 1 + a) & 0xFFFFFFFF
                d = c
                c = rotate_left(c, 4)

                current = set_LODWORD(current, d ^ c ^ current)

                e = (MAGIC_CONSTANTS[4*j + 1] + current) & 0xFFFFFFFF
                f = e
                e = rotate_left(e, 2)
                g = (f + 1 + e) & 0xFFFFFFFF
                h = g
                g = rotate_left(g, 8)
                i = (MAGIC_CONSTANTS[4*j + 2] + (h ^ g)) & 0xFFFFFFFF
                p = i
                i = rotate_left(i, 1)
                k = (i - p) & 0xFFFFFFFF
                l = k
                k = rotate_left(k, 16)

                current = set_HIDWORD(current, HIDWORD(current) ^ (current | l) ^ k)

                m = (MAGIC_CONSTANTS[4*j + 3] + HIDWORD(current)) & 0xFFFFFFFF
                n = m
                m = rotate_left(m, 2)

                current = set_LODWORD(current, ((n + 1 + m) ^ current) & 0xFFFFFFFF)

        previous = current
        mod_current = byte_swap(64, (current << 32) | HIDWORD(current))

        if needs_padding:
            remaining = bytearray(data[len(output):])

            for i in range(size):
                remaining[i] ^= mod_current & 0xFF
                mod_current >>= 8

            output += remaining
            break

        output += mod_current.to_bytes(8, 'little')

    return output


def encode(data):
    import base64

    # Non-standard base64 alphabet
    mapping = str.maketrans(
        'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/',
        '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz._'
    )

    # Output has no padding bytes
    return base64.b64encode(data).decode('ascii').translate(mapping).rstrip('=')


def extract_info(data):
    version = data.splitlines()[0]

    if not version.startswith('X Lossless Decoder version'):
        version = None
    else:
        version = version.split()[4]

    if '\n-----BEGIN XLD SIGNATURE-----\n' not in data:
        signature = None
    else:
        data, signature_parts = data.split('\n-----BEGIN XLD SIGNATURE-----\n', 1)
        signature = signature_parts.split('\n-----END XLD SIGNATURE-----\n')[0].strip()

    return data, version, signature


def xld_verify(data):
    data, version, old_signature = extract_info(data)

    hashed_data = (almost_sha256(data.encode('utf-8')) + '\nVersion=0001').encode('ascii')
    scrambled_data = scramble(hashed_data)
    signature = encode(scrambled_data)

    return data, version, old_signature, signature


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Verifies and resigns XLD logs')
    parser.add_argument('file', metavar='FILE', help='path to the log file')

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--verify', action='store_true', help='verify a log')
    group.add_argument('--sign', action='store_true', help='sign or fix an existing log')

    args = parser.parse_args()

    if args.file == '-':
        handle = sys.stdin
    else:
        handle = open(args.file, 'rb')

    data, version, old_signature, actual_signature = xld_verify(handle.read().decode('utf-8'))
    handle.close()

    if args.sign:
        if version <= LOGCHECKER_MIN_VERSION:
            raise ValueError('XLD version was too old to be signed')

        print(data)
        print('-----BEGIN XLD SIGNATURE-----')
        print(actual_signature)
        print('-----END XLD SIGNATURE-----')

    if args.verify:
        if old_signature is None:
            print('Not a log file')
            sys.exit(1)
        elif old_signature != actual_signature:
            print('Malformed')
            sys.exit(1)
        elif version <= LOGCHECKER_MIN_VERSION:
            print('Forged')
            sys.exit(1)
        else:
            print('OK')
