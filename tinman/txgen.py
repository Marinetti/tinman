#!/usr/bin/env python3

import argparse
import datetime
import hashlib
import itertools
import json
import os
import random
import sys

from . import prockey
from . import util

STEEM_GENESIS_TIMESTAMP = 1451606400
STEEM_BLOCK_INTERVAL = 3

def create_accounts(conf, keydb, name):
    desc = conf["accounts"][name]
    for index in range(desc.get("count", 1)):
        name = desc["name"].format(index=index)
        yield {"operations" : [["account_create",{
            "fee" : desc["vesting"],
            "creator" : desc["creator"],
            "new_account_name" : name,
            "owner" : keydb.get_authority(name, "owner"),
            "active" : keydb.get_authority(name, "active"),
            "posting" : keydb.get_authority(name, "posting"),
            "memo_key" : keydb.get_pubkey(name, "memo"),
            "json_metadata" : "",
           }]],
           "wif_sigs" : [keydb.get_privkey(desc["creator"])]}
    return

def vote_accounts(conf, keydb, elector, elected):
    er_desc = conf["accounts"][elector]
    ed_desc = conf["accounts"][elected]

    er_count = er_desc["count"]
    ed_count = ed_desc["count"]

    rr = itertools.cycle(range(ed_count))

    rand = random.Random(er_desc["randseed"])

    for er_index in range(er_desc["count"]):
        votes = []
        for i in range(er_desc["round_robin_votes_per_elector"]):
            votes.append(next(rr))
        for i in range(er_desc["random_votes_per_elector"]):
            votes.append(rand.randrange(0, ed_count))
        votes = sorted(set(votes))
        ops = []
        er_name = er_desc["name"].format(index=er_index)
        for ed_index in votes:
           ed_name = ed_desc["name"].format(index=ed_index)
           ops.append(["account_witness_vote", {
            "account" : er_name,
            "witness" : ed_name,
            "approve" : True,
            }])
        yield {"operations" : ops, "wif_sigs" : [keydb.get_privkey(er_name)]}
    return

def update_witnesses(conf, keydb, name):
    desc = conf["accounts"][name]
    for index in range(desc["count"]):
        name = desc["name"].format(index=index)
        yield {"operations" : [["witness_update",{
            "owner" : name,
            "url" : "https://steemit.com/",
            "block_signing_key" : "TST6LLegbAgLAy28EHrffBVuANFWcFgmqRMW13wBmTExqFE9SCkg4",
            "props" : {},
            "fee" : amount(0),
           }]],
           "wif_sigs" : [keydb.get_privkey(name)]}
    return

def build_setup_transactions(conf, keydb):
    yield from create_accounts(conf, keydb, "init")
    yield from create_accounts(conf, keydb, "elector")
    yield from create_accounts(conf, keydb, "manager")
    yield from create_accounts(conf, keydb, "porter")
    yield from port_snapshot(conf, keydb)

def build_initminer_tx(conf, keydb):
    return {"operations" : [
     ["account_update",
      {
       "account" : "initminer",
       "owner" : keydb.get_authority("initminer", "owner"),
       "active" : keydb.get_authority("initminer", "active"),
       "posting" : keydb.get_authority("initminer", "posting"),
       "memo_key" : keydb.get_pubkey("initminer", "memo"),
       "json_metadata" : "",
      }],
     ["transfer_to_vesting",
      {
       "from" : "initminer",
       "to" : "initminer",
       "amount" : conf["accounts"]["initminer"]["vesting"],
      }],
     ["account_witness_vote",
      {
       "account" : "initminer",
       "witness" : "initminer",
       "approve" : True,
      }],
    ],
    "wif_sigs" : ["5JNHfZYKGaomSFvd4NUdQ9qMcEAC43kujbfjueTHpVapX1Kzq2n"]}

def satoshis(s):
    return int(s[0])

def amount(satoshis, prec=3, symbol="@@000000021"):
    return [str(satoshis), prec, symbol]

def get_system_account_names(conf):
    for desc in conf["accounts"].values():
        for index in range(desc.get("count", 1)):
            name = desc["name"].format(index=index)
            yield name
    return

def port_snapshot(conf, keydb):
    with open(conf["snapshot_file"], "r") as f:
        snapshot = json.load(f)
    total_vests = 0
    total_steem = 0

    system_account_names = set(get_system_account_names(conf))

    def user_accounts():
        return (a for a in snapshot["accounts"] if a["name"] not in system_account_names)

    num_accounts = 0
    for acc in user_accounts():
        total_vests += satoshis(acc["vesting_shares"])
        total_steem += satoshis(acc["balance"])
        num_accounts += 1

    # We have a fixed amount of STEEM to give out, specified by total_port_balance
    # This needs to be given out subject to the following constraints:
    # - The ratio of vesting : liquid STEEM is the same on testnet,
    # - Everyone's testnet balance is proportional to their mainnet balance
    # - Everyone has at least min_vesting_per_account

    dgpo = snapshot["dynamic_global_properties"]
    denom = 10**12        # we need stupidly high precision because VESTS
    min_vesting_per_account = satoshis(conf["min_vesting_per_account"])
    total_vesting_steem = satoshis(dgpo["total_vesting_fund_steem"])
    total_port_balance = satoshis(conf["total_port_balance"])
    avail_port_balance = total_port_balance - min_vesting_per_account * num_accounts
    if avail_port_balance < 0:
        raise RuntimeError("Increase total_port_balance or decrease min_vesting_per_account")
    total_port_vesting = (avail_port_balance * total_vesting_steem) // (total_steem + total_vesting_steem)
    total_port_liquid = (avail_port_balance * total_steem) // (total_steem + total_vesting_steem)
    vest_conversion_factor  = (denom * total_port_vesting) // total_vests
    steem_conversion_factor = (denom * total_port_liquid ) // total_steem

    """
    print("total_vests:", total_vests)
    print("total_steem:", total_steem)
    print("total_vesting_steem:", total_vesting_steem)
    print("total_port_balance:", total_port_balance)
    print("total_port_vesting:", total_port_vesting)
    print("total_port_liquid:", total_port_liquid)
    print("vest_conversion_factor:", vest_conversion_factor)
    print("steem_conversion_factor:", steem_conversion_factor)
    """

    porter = conf["accounts"]["porter"]["name"]

    yield {"operations" : [
      ["transfer",
      {"from" : "initminer",
       "to" : porter,
       "amount" : conf["total_port_balance"],
       "memo" : "Fund porting balances",
      }]],
       "wif_sigs" : [keydb.get_privkey("initminer")]}

    porter_wif = keydb.get_privkey("porter")

    create_auth = {"account_auths" : [["porter", 1]], "key_auths" : [], "weight_threshold" : 1}

    for a in user_accounts():
        vesting_amount = (satoshis(a["vesting_shares"]) * vest_conversion_factor) // denom
        transfer_amount = (satoshis(a["balance"]) * steem_conversion_factor) // denom
        name = a["name"]
        tnman = conf["accounts"]["manager"]["name"]

        ops = [["account_create",{
          "fee" : amount(max(vesting_amount, min_vesting_per_account)),
          "creator" : porter,
          "new_account_name" : name,
          "owner" : create_auth,
          "active" : create_auth,
          "posting" : create_auth,
          "memo_key" : "TST"+a["memo_key"][3:],
          "json_metadata" : "",
         }]]
        if transfer_amount > 0:
            ops.append(["transfer",{
             "from" : porter,
             "to" : name,
             "amount" : amount(transfer_amount),
             "memo" : "Ported balance",
             }])

        yield {"operations" : ops, "wif_sigs" : [porter_wif]}

    for a in user_accounts():
        cur_auth = json.loads(json.dumps(a["posting"]))
        non_existing_account_auths = []
        # filter to only include existing accounts
        cur_auth["account_auths"] = [aw for aw in cur_auth["account_auths"] if
           (aw in snapshot["accounts"]) and (aw not in system_account_names)]

        # add tnman to account_auths
        cur_auth["account_auths"].append([tnman, cur_auth["weight_threshold"]])
        # substitute prefix for key_auths
        cur_auth["key_auths"] = [["TST"+k[3:], w] for k, w in cur_auth["key_auths"]]

        ops = [["account_update",{
          "account" : a["name"],
          "owner" : cur_auth,
          "active" : cur_auth,
          "posting" : cur_auth,
          "memo_key" : "TST"+a["memo_key"][3:],
          "json_metadata" : a["json_metadata"],
          }]]

        yield {"operations" : ops, "wif_sigs" : [porter_wif]}

    return

def build_actions(conf):
    keydb = prockey.ProceduralKeyDatabase()

    start_time = datetime.datetime.strptime(conf["start_time"], "%Y-%m-%dT%H:%M:%S")
    genesis_time = datetime.datetime.utcfromtimestamp(STEEM_GENESIS_TIMESTAMP)
    miss_blocks = int((start_time - genesis_time).total_seconds()) // STEEM_BLOCK_INTERVAL
    miss_blocks = max(miss_blocks-1, 0)

    yield ["wait_blocks", {"count" : 1, "miss_blocks" : miss_blocks}]
    yield ["submit_transaction", {"tx" : build_initminer_tx(conf, keydb)}]
    for b in util.batch(build_setup_transactions(conf, keydb), conf["transactions_per_block"]):
        yield ["wait_blocks", {"count" : 1}]
        for tx in b:
            yield ["submit_transaction", {"tx" : tx}]

    for tx in update_witnesses(conf, keydb, "init"):
        yield ["submit_transaction", {"tx" : tx}]
    for tx in vote_accounts(conf, keydb, "elector", "init"):
        yield ["submit_transaction", {"tx" : tx}]
    yield ["wait_blocks", {"count" : 1000000000}]

    return

def main(argv):
    parser = argparse.ArgumentParser(prog=argv[0], description="Generate transactions for Steem testnet")
    parser.add_argument("-c", "--conffile", default="", dest="conffile", metavar="FILE", help="Specify configuration file")
    parser.add_argument("-o", "--outfile", default="-", dest="outfile", metavar="FILE", help="Specify output file, - means stdout")
    args = parser.parse_args(argv[1:])

    with open(args.conffile, "r") as f:
        conf = json.load(f)

    if args.outfile == "-":
        outfile = sys.stdout
    else:
        outfile = open(args.outfile, "w")

    for action in build_actions(conf):
        outfile.write(util.action_to_str(action))
        outfile.write("\n")

    outfile.flush()
    if args.outfile != "-":
        outfile.close()

if __name__ == "__main__":
    main(sys.argv)
