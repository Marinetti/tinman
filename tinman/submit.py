#!/usr/bin/env python3

from tinman.simple_steem_client.simple_steem_client.client import SteemRemoteBackend, SteemInterface

from binascii import hexlify, unhexlify

import argparse
import datetime
import hashlib
import itertools
import json
import struct
import subprocess
import sys
import time
import traceback

from . import util

class TransactionSigner(object):
    def __init__(self, sign_transaction_exe=None, chain_id=None):
        if(chain_id is None):
            self.proc = subprocess.Popen([sign_transaction_exe], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        else:
            self.proc = subprocess.Popen([sign_transaction_exe, "--chain-id="+chain_id], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        return

    def sign_transaction(self, tx, wif):
        json_data = json.dumps({"tx":tx, "wif":wif}, separators=(",", ":"), sort_keys=True)
        json_data_bytes = json_data.encode("ascii")
        self.proc.stdin.write(json_data_bytes)
        self.proc.stdin.write(b"\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        return json.loads(line)

class CachedDgpo(object):
    def __init__(self, timefunc=time.time, refresh_interval=1.0, steemd=None):
        self.timefunc = timefunc
        self.refresh_interval = refresh_interval
        self.steemd = steemd

        self.dgpo = None
        self.last_refresh = self.timefunc()

        return

    def reset(self):
        self.dgpo = None

    def get(self):
        now = self.timefunc()
        if (now - self.last_refresh) > self.refresh_interval:
            self.reset()
        if self.dgpo is None:
            self.dgpo = self.steemd.database_api.get_dynamic_global_properties(a=None)
            self.last_refresh = now
        return self.dgpo

def main(argv):

    parser = argparse.ArgumentParser(prog=argv[0], description="Submit transactions to Steem")
    parser.add_argument("-t", "--testserver", default="http://127.0.0.1:8190", dest="testserver", metavar="URL", help="Specify testnet steemd server with debug enabled")
    parser.add_argument("--signer", default="sign_transaction", dest="sign_transaction_exe", metavar="FILE", help="Specify path to sign_transaction tool")
    parser.add_argument("-i", "--input-file", default="-", dest="input_file", metavar="FILE", help="File to read transactions from")
    parser.add_argument("-f", "--fail-file", default="-", dest="fail_file", metavar="FILE", help="File to write failures, - for stdout, die to quit on failure")
    args = parser.parse_args(argv[1:])

    die_on_fail = False
    if args.fail_file == "-":
        fail_file = sys.stdout
    elif args.fail_file == "die":
        fail_file = sys.stdout
        die_on_fail = True
    else:
        fail_file = open(args.fail_file, "w")

    if args.input_file == "-":
        input_file = sys.stdin
    else:
        input_file = open(args.input_file, "r")

    backend = SteemRemoteBackend(nodes=[args.testserver], appbase=True)
    steemd = SteemInterface(backend)
    sign_transaction_exe = args.sign_transaction_exe

    cached_dgpo = CachedDgpo(steemd=steemd)

    chain_id_name = b"testnet"
    chain_id = hashlib.sha256(chain_id_name).digest()

    signer = TransactionSigner(sign_transaction_exe=sign_transaction_exe, chain_id=chain_id)

    for line in input_file:
        line = line.strip()
        cmd, args = json.loads(line)

        try:
            if cmd == "wait_blocks":
                steemd.debug_node_api.debug_generate_blocks(
                    debug_key="5JNHfZYKGaomSFvd4NUdQ9qMcEAC43kujbfjueTHpVapX1Kzq2n",
                    count=args["count"],
                    skip=0,
                    miss_blocks=args.get("miss_blocks", 0),
                    edit_if_needed=False,
                    )
                cached_dgpo.reset()
            elif cmd == "submit_transaction":
                tx = args["tx"]
                dgpo = cached_dgpo.get()
                tx["ref_block_num"] = dgpo["head_block_number"] & 0xFFFF
                tx["ref_block_prefix"] = struct.unpack_from("<I", unhexlify(dgpo["head_block_id"]), 4)[0]
                head_block_time = datetime.datetime.strptime(dgpo["time"], "%Y-%m-%dT%H:%M:%S")
                expiration = head_block_time+datetime.timedelta(minutes=1)
                expiration_str = expiration.strftime("%Y-%m-%dT%H:%M:%S")
                tx["expiration"] = expiration_str

                wif_sigs = tx["wif_sigs"]
                del tx["wif_sigs"]

                sigs = []
                for wif in wif_sigs:
                    if not isinstance(wif_sigs, list):
                        raise RuntimeError("wif_sigs is not list")
                    result = signer.sign_transaction(tx, wif)
                    if "error" in result:
                        print("could not sign transaction", tx, "due to error:", result["error"])
                    else:
                        sigs.append(result["result"]["sig"])
                tx["signatures"] = sigs
                print("bcast:", json.dumps(tx, separators=(",", ":")))

                steemd.network_broadcast_api.broadcast_transaction(trx=tx)
        except Exception as e:
            fail_file.write(json.dumps([cmd, args, str(e)])+"\n")
            fail_file.flush()
            if die_on_fail:
                raise

if __name__ == "__main__":
    main(sys.argv)