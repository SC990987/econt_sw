import uhal
import time
import argparse
import numpy as np
import logging
logging.basicConfig()

from uhal_config import names,input_nlinks,output_nlinks

from uhal_utils import check_links,read_testvector,get_captured_data,save_testvector,check_IO,configure_acquire,do_capture

"""
Event DAQ using uHAL python2.

Usage:
   python testing/uhal-eventDAQ.py --idir INPUTDIR
"""

if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("-L", "--logLevel", dest="logLevel",action="store",
                        help="log level which will be applied to all cmd : ERROR, WARNING, DEBUG, INFO, NOTICE, NONE",default='NONE')
    parser.add_argument("--capture", dest="capture", action="store",
                        help="capture data with one of the options", choices=["l1a","compare","bx"], required=True)
    parser.add_argument('--idir',dest="idir",type=str, required=True, help='test vector directory')    
    args = parser.parse_args()

    if args.logLevel.find("ERROR")==0:
        uhal.setLogLevelTo(uhal.LogLevel.ERROR)
    elif args.logLevel.find("WARNING")==0:
        uhal.setLogLevelTo(uhal.LogLevel.WARNING)
    elif args.logLevel.find("NOTICE")==0:
        uhal.setLogLevelTo(uhal.LogLevel.NOTICE)
    elif args.logLevel.find("DEBUG")==0:
        uhal.setLogLevelTo(uhal.LogLevel.DEBUG)
    elif args.logLevel.find("INFO")==0:
        uhal.setLogLevelTo(uhal.LogLevel.INFO)
    else:
        uhal.disableLogging()

    man = uhal.ConnectionManager("file://connection.xml")
    dev = man.getDevice("mylittlememory")

    logger = logging.getLogger('eventDAQ')
    logger.setLevel(logging.INFO)

    # first, check alignment
    is_fromIO_aligned = check_IO(dev,io='from',nlinks=output_nlinks)
    # with current firmware lc ASIC counters do not show alignment
    #is_lcASIC_aligned = check_links(dev,lcapture='lc-ASIC',nlinks=output_nlinks)
    #if not is_fromIO_aligned or not is_lcASIC_aligned:
    #    print('not aligned! Exiting...')
    #exit(1)

    # read latency values from aligned link captures
    latency_values = {}
    for lcapture in ['lc-ASIC','lc-emulator']:
        latency_values[lcapture] = []
        for l in range(output_nlinks):
            latency = dev.getNode(names[lcapture]['lc']+".link"+str(l)+".fifo_latency").read();
            dev.dispatch()
            latency_values[lcapture].append(int(latency))
    # print('FIFO latency: ',latency_values)
    #for l in range(output_nlinks):
    #    latency_values['lc-emulator'][l] = 3
    #print(latency_values)

    # setup test-vectors
    out_brams = []
    testvectors_settings = {
        "switch": {"output_select": 0x0,
                   "n_idle_words": 255,
                   "idle_word": 0xaccccccc,
                   "idle_word_BX0": 0x9ccccccc,
                   "header_mask": 0x00000000, # do not set headers
                   "header": 0xa0000000,
                   "header_BX0": 0x90000000,
                   },
        "stream": {"sync_mode": 0x1,
                   "ram_range": 0x1,
                   "force_sync": 0x0,
                   }
    }
    for l in range(input_nlinks):
        for st in ['switch','stream']:
            for key,value in testvectors_settings[st].items():
                dev.getNode(names['testvectors'][st]+".link"+str(l)+"."+key).write(value)
            
        # size of bram is 4096
        out_brams.append([None] * 4096)
        
        dev.dispatch()

    # set input data
    fname = args.idir+"/../testInput.csv"
    data = read_testvector(fname)
    for l in range(input_nlinks):
        for i,b in enumerate(out_brams[l]):
            out_brams[l][i] = int(data[l][i%3564],16)
        dev.getNode(names['testvectors']['bram'].replace('00',"%02d"%l)).writeBlock(out_brams[l])
    dev.dispatch()
    time.sleep(0.001)

    # configure bypass to take data from test-vectors
    for l in range(output_nlinks):
        dev.getNode(names['bypass']['switch']+".link"+str(l)+".output_select").write(0x1)
    dev.dispatch()

    # configure delay again?
    delay = 4
    dev.getNode(names['delay']+".delay").write(delay)

    # configure fast commands
    dev.getNode(names['fc']+".command.enable_fast_ctrl_stream").write(0x1);
    dev.getNode(names['fc']+".command.enable_orbit_sync").write(0x1);

    # configure link capture to capture on L1A
    acq_length = 300
    for lcapture in ['lc-input','lc-ASIC','lc-emulator']:
        nlinks = input_nlinks if 'input' in lcapture else output_nlinks
        configure_acquire(dev,lcapture,"L1A",nwords=acq_length,nlinks=nlinks)
        
        # set latency?
        """
        if 'input' not in lcapture:
            for l in range(input_nlinks):
                print('writing ',lcapture,l,latency_values[lcapture][l])
                dev.getNode(names[lcapture]['lc']+".link"+str(l)+".fifo_latency").write(latency_values[lcapture][l])
                dev.dispatch()
                lat = dev.getNode(names[lcapture]['lc']+".link"+str(l)+".fifo_latency").read()
                dev.dispatch()
                print(lcapture,l,int(lat))
        """
    # check stream compare
    dev.getNode(names['stream_compare']+".control.reset").write(0x1)
    time.sleep(0.001)
    dev.getNode(names['stream_compare']+".control.latch").write(0x1)
    dev.dispatch()
    word_count = dev.getNode(names['stream_compare']+".word_count").read()
    err_count = dev.getNode(names['stream_compare']+".err_count").read()
    dev.dispatch()
    logger.info('Stream compare, word count %d, error count %d'%(word_count,err_count))

    if args.capture == "l1a":
        # send L1A
        dev.getNode(names['fc']+".command.global_l1a_enable").write(1);
        dev.getNode(names['fc']+".periodic0.enable").write(0); # to get a L1A once - not every orbit
        dev.getNode(names['fc']+".periodic0.flavor").write(0); # 0 to get a L1A
        dev.getNode(names['fc']+".periodic0.enable_follow").write(0); # does not depend on other generator
        dev.getNode(names['fc']+".periodic0.bx").write(3500);
        dev.getNode(names['fc']+".periodic0.request").write(1);
        dev.dispatch()

    elif args.capture == "compare":
        # send a L1A with two capture blocks 
        dev.getNode(names['stream_compare']+".trigger").write(0x1)
        dev.dispatch()

    else:
        logger.error("No capture mode provided")

    # tell link capture to do an acquisition
    all_data = {}
    for lcapture in ['lc-input','lc-ASIC','lc-emulator']:
        nlinks = input_nlinks if 'input' in lcapture else output_nlinks
        do_capture(dev,lcapture)
        all_data[lcapture] = get_captured_data(dev,lcapture,nwords=acq_length,nlinks=nlinks)

    # convert all data to format
    for key,data in all_data.items():
        # print('saving %s/%s-Output_header.csv'%(args.idir,key))
        save_testvector( args.idir+"/%s-Output_header.csv"%key, data, header=True)

    # reset fc
    dev.getNode(names['fc']+".command.global_l1a_enable").write(0);
