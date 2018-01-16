
# Overview

The `tinman` set of utilities is a set of scripts to create a testnet.
A `tinman` testnet allows all, or some subset of, user accounts to
easily be *ported* from the main network.

# Tinman commands

This repository contains utilities to create a testnet.

`tinman snapshot` : Gets account data and other data from the blockchain as necessary to do offline initialization of testnet
`tinman txgen` : Translate the output of `snapshot.py` to a set of actions to perform offline initialization of testnet
`tinman keysub` : Substitute secret keys into a list of actions
`tinman submit` : Submit the output of `txgen.py` to testnet node

# Installation

The installation process for `tinman` is complicated and finicky because the
Python packaging of `steem-python` is
[complicated and finicky](https://github.com/steemit/steem-python/issues/96).

## Compiling Python

The Python which comes with Ubuntu 16.04 is too old.  So we must download,
build and install a newer version from `python.org`:

```
sudo apt-get install build-essential libbz2-dev libssl-dev libreadline-dev libsqlite3-dev tk-dev wget xz-utils
wget https://www.python.org/ftp/python/3.6.3/Python-3.6.3.tar.xz
cat >> Python-3.6.3.tar.xz.sha256sum <<EOF
cda7d967c9a4bfa52337cdf551bcc5cff026b6ac50a8834e568ce4a794ca81da *Python-3.6.3.tar.xz
EOF
sha256sum -c Python-3.6.3.tar.xz.sha256sum
xz -cd Python-3.6.3.tar.xz | tar x
cd Python-3.6.3
./configure "--prefix=$HOME/opt/python-3.6.3"
make -j$(nproc)
make install
```

## Creating a virtualenv

In this step we create a virtualenv to isolate our project from the
system-wide Python installation.  The virtualenv is *activated*,
modifying the `PATH` and the prompt of the current shell,
by sourcing the `activate` script:

```
sudo apt-get install virtualenv
virtualenv -p "$HOME/opt/python-3.6.3/bin/python3.6" ~/ve/tinman
source ~/ve/tinman/bin/activate
```

Then we can install `python-steem` using the `pip` within the
active virtualenv (i.e., in a shell where the `~/ve/tinman/bin/activate`
script has been sourced).  We need unmerged changes in the
`theoretical-testnet` branch of the git repo, so use the following
command:

```
# Execute inside tinman virtualenv
pip install git+https://github.com/steemit/steem-python.git@theoretical-testnet
```

## Checking out the tinman source

The `tinman` source can be checked out with `git`.  This documentation
assumes the source code lives in `~/src/tinman`:

```
mkdir -p ~/src
cd ~/src
git clone https://github.com/steemit/tinman
```

If everything is set up correctly, you should be able to run commands
such as `tinman help` as follows:

```
# Execute inside tinman virtualenv
cd ~/src/tinman
python -m tinman help
```

## Setting up tinman script

It is inconvenient to always change to the `tinman` directory
and invoke `python -m tinman` manually.  So these commands will
set up a shell script shortcut called `tinman`:

```
mkdir -p ~/bin
cat >~/bin/tinman <<'EOF'
#!/bin/sh
exec env PYTHONPATH="$HOME/src/tinman" "$HOME/ve/tinman/bin/python" -m tinman "$@"
EOF
chmod a+x ~/bin/tinman
```

You will also have to add `$HOME/bin` to your `PATH` to your shell startup
script if it is not already there.  (It is present in the
default shell startup scripts on Ubuntu 16.04.)

If it is all set up correctly, you should be able to execute the following
commands and see the help for the `tinman snapshot` command, even if the
virtualenv is not active:

```
#
# Execute inside or outside tinman virtualenv
#

cd ~
tinman snapshot --help
```

(Hint:  If you are inside a virtualenv, you may type `deactivate`
to exit the virtualenv without exiting the shell.)

# Example usage

This section contains a single large example.

## Mainnet steemd

First, we set up a `steemd` for the main network.  This `steemd` must be the following characteristics:

- The `steemd` must be `appbase` version
- The `chain`, `webserver` and `database_api` plugins must be enabled
- The `webserver-http-endpoint` assumed by the following examples is `127.0.0.1:8090`
- If a snapshot at a well-defined single point in time is desired, no seed nodes should be used, so it does not connect to the p2p network

## Taking a snapshot

```
tinman snapshot -s http://127.0.0.1:8090 -o snapshot.json
```

As of this writing, the above command takes approximately 5 minutes, writing an approximately 1 GB JSON file with 500,000 lines.
If you're running `tinman snapshot` interactively and you would like a visual progress indicator, you can install the `pv` program
(`apt-get install pv`) and use it to display the output line count in real time:

```
tinman snapshot -s http://127.0.0.1:8090 | pv -l > snapshot.json
```

# Generating actions

Now you can use `tinman txgen` to create a list of *actions*.  Actions include
transactions which create and fund the accounts, and wait-for-block instructions
which control the rate at which transactions occur:

```
# As of this writing, this command takes ~10 minutes, consumes ~4GB of RAM
tinman txgen -c txgen.conf -o tn.txlist
```

Some notes about `tinman txgen`:

- All accounts have `porter` as an additional authority, allowing the testnet creator to act as any account on the testnet
- The private keys for `porter` and other accounts are deterministically created based on the `secret` option in the config file
- Balances are created by dividing `total_port_balance` proportionally among the live STEEM and vesting, subject to `min_vesting_per_account`.
- Therefore, testnet balance is not equal to mainnet balance.  Rather, it is proportional to mainnet balance.
- Accounts listed in `txgen.conf` are considered system accounts, any identically named account in the snapshot will not be ported

# Keys substitution

To maintain separation of concerns in `tinman` tools, the `tinman txgen` tool
does not directly generate transactions containing private keys (except
the `STEEM_INIT_PRIVATE_KEY` WIF, `5JNHfZYKGaomSFvd4NUdQ9qMcEAC43kujbfjueTHpVapX1Kzq2n`).
Instead *keystrings* such as `publickey:active-porter` are outputted in place
of the actual public key of the `porter` account.

Since transactions can contain arbitrary user-specified data, a fixed
escape sequence cannot be used to delimit keystrings, since it might appear
in user-specified data.  Instead, a variable escape sequence (a short value
that does not appear in the data) is introduced and stored in the `"esc"`
variable.

So a program that knows the keys must substitute them before the transactions
can be submitted to the network.  This is the role of the key substitution tool
`tinman keysub`.  The `tinman keysub` tool takes as input a list of actions,
generates the specified keys, and substitutes them into each action.

## Deriving secret keys

By default, the private keys generated by `tinman keysub` have
known (i.e. insecure) seed strings.  However, a secret may be
added to each seed string by prepending a `set_secret` action
to `tinman keysub`.

## Command-line key generator

The `get_dev_key` program provided with `steemd` derives
keys using the same algorithm as `tinman keysub`.

# Running testnet fastgen node

Now that the transactions have been created, let's use them to initialize a testnet.
Since many blocks worth of transactions are created, `tinman submit` will
implement the block wait using `debug_node_plugin` to generate blocks in the
past as rapidly as possible.  So we will run a special node, let's call it the
"fastgen node", with the debug plugin enabled.  The fastgen node is only used to
initialize the network.  (It is called "fastgen" because it generates blocks
as fast as possible, rather than waiting 3 seconds of real time between each
block.)  Later, one or more normal witness nodes will connect
to the fastgen node over p2p, get blocks, and begin normal block production.

The fastgen node needs the following:

- The `steemd` must be `appbase` version
- The testnet `blockchain` directory should be empty (try `rm -Rf testnet_datadir/blockchain`)
- The following plugins should be enabled:  `chain p2p webserver debug_node database_api network_broadcast_api debug_node_api block_api`
- The `webserver-http-endpoint` assumed by the following examples is `127.0.0.1:9990`
- It must contain functionality from PR's #1722 #1723
- It should listen for p2p, the following examples assume it is listening on `0.0.0.0:12001`

On the testnet, some serializations are different from the main network, and
[they are not handled properly by steem_python](https://github.com/steemit/steem-python/issues/89).
Therefore, `tinman submit` outsources signing of those transactions to the
`sign_transaction` binary included with `steemd`.

# Pipelining transactions to testnet

```
( \
  echo '["set_secret", {"secret":"xyz-"}]' ; \
  tinman txgen -c txgen.conf \
) | \
tinman keysub | \
tinman submit -t http://127.0.0.1:9990 --signer steem/programs/util/sign_transaction -f fail.json
```

# Running testnet witness node(s)

At the end of the transactions to be submitted, `tinman txgen` creates witnesses `init-0` through `init-20`
and votes for them with large amount of `TESTS`.  The keys of these witnesses are generated by a deterministic
algorithm compatible with the `get_dev_key` utility program, so the keys of the witnesses may be obtained
as follows:

```
programs/util/get_dev_key xxx- block-init-0:21
```

where `xxx` is the `"secret"` string in `txgen.conf`.

So in order to transition block production duties away from the initial node, all that is required
is to connect witness nodes with the correct block production settings.  Each witness node should
specify the fastgen node using the `p2p-seed-node` option in the config file.

Therefore we may add the witness definitions and private keys to the witness config file:

```
i=0 ; while [ $i -lt 21 ] ; do echo witness = '"'init-$i'"' >> testnet_datadir/config.ini ; let i=i+1 ; done
steem/programs/util/get_dev_key xxx- block-init-0:21 | cut -d '"' -f 4 | sed 's/^/private-key = /' >> testnet_datadir/config.ini
```

Witness duties may of course be split among multiple nodes if desired, simply put the
`witness` and `private-key` definitions in the datadir of each node, and have each
witness node connect to all the others with the `p2p-seed-node` option.

Additionally, because there is a large gap in block timestamps between the end of the
initialization blocks and the beginning of normal production, the witness will need
to specify `--enable-stale-production` and `--required-participation=0` flags.  As
long as a sufficient number of other witness nodes are timely producing blocks, it
is not necessary to use these flags once 128 blocks have been produced after the
transition.