import uhal
import argparse
import logging
logging.basicConfig()

from time import sleep

logger = logging.getLogger('fc')

import utils.fast_command as utils_fc
from utils.uhal_config import *

"""
Send/Read fast commands
"""

def command_delay(dev):
    dev.getNode(names['fc']+".command_delay").write(1);
    dev.dispatch()

if __name__ == "__main__":    
    parser = argparse.ArgumentParser(description='Align links')
    parser.add_argument("-L", "--logLevel", dest="logLevel",action="store",
                        help="log level which will be applied to all cmd : ERROR, WARNING, DEBUG, INFO, NOTICE",default='INFO')
    parser.add_argument('--fc', type=str, required=True, 
                        choices=['chipsync','command-delay'],
                        help='fast command')
    parser.add_argument('--read', action='store_true', default=False, help='read')
    args = parser.parse_args()

    set_logLevel(args)
    man = uhal.ConnectionManager("file://connection.xml")
    dev = man.getDevice("mylittlememory")

    try:
        logger.setLevel(args.logLevel)
    except ValueError:
        logging.error("Invalid log level")
        exit(1)

    utils_fc.configure_fc(dev,args.read)
    if args.fc=='chipsync':
        utils_fc.chipsync(dev)
    elif args.fc=='command-delay':
        command_delay(dev)
