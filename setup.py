from setuptools import setup

setup(name="tinman",
      version          = 0.1,
      description      = "Testnet management scripts.",
      url              = "https://github.com/steemit/tinman",
      author           = "Steemit",
      packages         = ["tinman", "tinman.simple_steem_client", "tinman.simple_steem_client.simple_steem_client"],
      install_requires = [],
      entry_points     = {"console_scripts" : [
                          "tinman=tinman.main:sys_main",
                         ]}
    )
