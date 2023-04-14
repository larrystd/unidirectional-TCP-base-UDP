import logging
import time
# create logger
logger = logging.getLogger('simple_example')
logger.setLevel(logging.INFO)

# create console handler and set level to debug
ch = logging.StreamHandler()
ch = logging.FileHandler('1', 'w+')
ch.setLevel(logging.INFO)
# add ch to logger
logger.addHandler(ch)

# 'application' code
logger.info('info message')

print (round(time.time() * 1000,2))
print (round(0.234,2))
t_start = time.time()
time.sleep(2)
print (time.time() - t_start)

l = [1,2,3,4,5]
print (l[1:4])

s = 'abc'
print (f'ab {s}')

import random

print (random.uniform(0, 1))

for i in range(10):
    print(random.random())
    
import logging
import threading
import time
import concurrent.futures

def thread_function(name):
    logging.info("Thread %s: starting", name)
    time.sleep(2)
    logging.info("Thread %s: finishing", name)

format = "%(asctime)s: %(message)s"
logging.basicConfig(format=format, level=logging.INFO,
                    datefmt="%H:%M:%S")
"""
logging.info("Main    : before creating thread")
x = threading.Thread(target=thread_function, args=(1,))
logging.info("Main    : before running thread")
x.start()
logging.info("Main    : wait for the thread to finish")
x.join()
logging.info("Main    : all done")
"""
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
    executor.map(thread_function, range(3))