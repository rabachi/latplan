#!/usr/bin/env python3

import random
import numpy as np
import os
import os.path
import sys
sys.path.append('../../')
from latplan.util import curry
from latplan.util.noise import gaussian, salt, pepper, saltpepper

import matplotlib
matplotlib.use('Agg')
import tensorflow as tf
import keras.backend as K
tf.logging.set_verbosity(tf.logging.ERROR)
# K.set_floatx('float16')
print("Default float: {}".format(K.floatx()))

def add_missingness(image_stack, prob_vis):
    '''Mask out pixels of the image stack according to 1-prob_vis'''
    rand_samps = np.random.random(size=(image_stack.reshape(image_stack.shape[0],-1)).shape)
    vis_masks = 1.0*np.less(rand_samps, prob_vis).reshape(image_stack.shape)
    masked_imgs = np.multiply(image_stack, vis_masks)
    return masked_imgs

def load_session():
    K.set_session(
        tf.Session(
            config=tf.ConfigProto(
                allow_soft_placement=True,
                gpu_options =
                tf.GPUOptions(
                    per_process_gpu_memory_fraction=1.0,
                    allow_growth=True,))))

load_session()

def identity(x):
    return x

steps     = 5
instances = 100
noise_fns     = [identity]
output_dirs = ["vanilla"]

def dijkstra(init_c,length,successor_fn):
    import queue
    open_list = queue.PriorityQueue()
    close_list = {}

    t = tuple(init_c)
    open_list.put((0, t))
    close_list[t] = {"g":0, "open":True,}

    expanded = 0
    g_max = -1
    
    while not open_list.empty():
        expanded += 1
        g, current = open_list.get()
        if g > length:
            print("explored all nodes with g < {}".format(length))
            return
        if g == length:
            yield current
        if g > g_max:
            print("new g",g,"expanded",expanded)
            g_max = g
                
        close_list[current]["open"]=False
        g_new = g+1
        
        for succ in successor_fn(current):
            succ = tuple(succ)
            if succ in close_list:
                node = close_list[succ]
                if node["open"] == False:
                    continue
                if g_new < node["g"]:
                    node["g"]    = g_new
                    node["open"] = True
                    open_list.put((g_new,succ))
            else:
                close_list[succ] = {"g":g_new, "open":True,}
                open_list.put((g_new,succ))
    print("open list exhausted")
    return

# XXX do not use, still results in suboptimal paths???
def lightsout_special(init_c,length,successor_fn):
    # generating lightout with dijkstra is extremely memory-demanding, as each node has 25 successors.
    # however, lightsout plans are order-invariant, so we can sample instances easily

    leds = len(init_c)

    import itertools
    for plan in itertools.combinations(range(leds), length):
        current = tuple(init_c)
        for action in plan:
            current = successor_fn(current)[action]
        print(current,plan)
        yield current

def reservoir_sampling(generator, limit):
    # perform a reservoid sampling because for a large W/H it is impossible to enumerate them in memory
    if limit is None:
        results = np.array(list(generator))
    else:
        results = np.array([ c for c,_ in zip(generator, range(limit)) ])
        i = limit
        step = 1
        for result in generator:
            i += 1
            if (i % step) == 0:
                if i == step * 10:
                    step = i
            j = random.randrange(i)
            if j < limit:
                results[j] = result
        print("done reservoir sampling")
    return results

def safe_chdir(path):
    try:
        os.mkdir(path)
    except:
        pass
    os.chdir(path)

def generate(p, ics, gcs, prob_vis, *args):
    import imageio
    import subprocess
    import datetime
    inits = add_missingness(p.generate(np.array(ics),*args), prob_vis)
    goals = add_missingness(p.generate(np.array(gcs),*args), prob_vis)
    for noise_fn,output_dir in zip(noise_fns,output_dirs):
        inits = noise_fn(inits)
        goals = noise_fn(goals)
        for i,init in enumerate(inits):
            for j,goal in enumerate(goals):
                d = "{}/{}/planning_{}/{:03d}-{:03d}-{:03d}".format(output_dir,p.__name__,prob_vis,steps,i,j)
                try:
                    subprocess.call(["mv",d,d+"_old_"+datetime.datetime.today().isoformat()])
                except:
                    pass
                os.makedirs(d)
                print(d)
                imageio.imsave(os.path.join(d,"init.png"),init)
                imageio.imsave(os.path.join(d,"goal.png"),goal)

################################################################

def puzzle(type='mnist', width=3, height=3, prob_vis=1.0):
    import importlib
    p = importlib.import_module('latplan.puzzles.puzzle_{}'.format(type))
    p.setup()
    ics = reservoir_sampling(dijkstra(np.arange(width*height), steps,
                                      lambda config: p.successors(config,width,height)),
                             instances)
    gcs = np.arange(width*height).reshape((1,width*height))
    generate(p, ics, gcs, prob_vis, width, height)

def puzzle_longest(type='mnist', width=3, height=3, prob_vis=1.0):
    global output_dirs
    output_dirs = ["longest"]
    import importlib
    p = importlib.import_module('latplan.puzzles.puzzle_{}'.format(type))
    p.setup()
    ics = [
        # from Reinfield '93
        # [8,0,6,5,4,7,2,3,1], # the second instance with the longest optimal solution 31
        [3,5,6,8,4,7,2,1,0],
        # [8,7,6,0,4,1,2,5,3], # the first instance with the longest optimal solution 31
        [1,8,6,7,4,3,2,5,0],
        # [8,5,6,7,2,3,4,1,0], # the first instance with the most solutions
        [8,7,4,5,6,1,2,3,0],
        # [8,5,4,7,6,3,2,1,0], # the second instance with the most solutions
        [8,7,6,5,2,1,4,3,0],
        # [8,6,7,2,5,4,3,0,1], # the "wrong"? hardest eight-puzzle from
        [7,8,3,6,5,4,1,2,0],
        # [6,4,7,8,5,0,3,2,1], # w01fe.com/blog/2009/01/the-hardest-eight-puzzle-instances-take-31-moves-to-solve/
        [5,8,7,6,1,4,0,2,3],
    ]
    gcs = np.arange(width*height).reshape((1,width*height))
    generate(p, ics, gcs, prob_vis, width, height)

def hanoi(disks=5, towers=3, prob_vis=1.0):
    import latplan.puzzles.hanoi as p
    p.setup()
    ics = [
        np.zeros(disks,dtype=int),
        *reservoir_sampling(dijkstra(np.full(disks,towers-1,dtype=int), steps,
                                     lambda config: p.successors(config,disks,towers)),
                            instances-1)
    ]
    gcs = np.full((1,disks),towers-1,dtype=int)
    generate(p, ics, gcs, prob_vis, disks, towers)

def lightsout(type='digital', size=4, prob_vis=1.0):
    import importlib
    p = importlib.import_module('latplan.puzzles.lightsout_{}'.format(type))
    p.setup()
    ics = reservoir_sampling(dijkstra(np.full(size*size,-1), steps,
                                      lambda config: p.successors(config)),
                             instances)
    gcs = np.full((1,size*size),-1)
    generate(p, ics, gcs, prob_vis)

################################################################

def noise(fn, param, domain, *args):
    noise_fns.append(lambda a: fn(a,param))
    output_dirs.append(fn.__name__)
    domain(*args)

################################################################

def main():
    import sys
    try:
        print('args:',sys.argv)
        def myeval(str):
            try:
                return eval(str)
            except:
                return str
        
        global steps, instances
        steps = myeval(sys.argv[1])
        instances = myeval(sys.argv[2])
        task      = myeval(sys.argv[3])
    except:
        print(sys.argv[0], 'steps','instances','task','[task-specific args...]')
    task(*map(myeval,sys.argv[4:]))

if __name__ == '__main__':
    try:
        main()
    except:
        import latplan.util.stacktrace
        latplan.util.stacktrace.format()

