#!/usr/bin/env python3

import config
import numpy as np
import numpy.random as random
from model import GumbelAE, ConvolutionalGumbelAE, \
    GaussianGumbelAE, GaussianConvolutionalGumbelAE

import keras.backend as K
from keras.optimizers import Adam
import tensorflow as tf

float_formatter = lambda x: "%.5f" % x
np.set_printoptions(formatter={'float_kind':float_formatter})

def curry(fn,*args1,**kwargs1):
    return lambda *args,**kwargs: fn(*args1,*args,**{**kwargs1,**kwargs})

def anneal_rate(epoch,min=0.1,max=5.0):
    import math
    return (2 / (epoch * (epoch+1))) * math.log(max/min)

default_networks = {'fc':GumbelAE,'conv':ConvolutionalGumbelAE,
                    'fcg':GaussianGumbelAE,'convg':GaussianConvolutionalGumbelAE}
encoder = 'fc'

epoch = 1000
batch_size = 2000

max_temperature = 1.0
def learn_model(path,train_data,test_data=None,network=None):
    if network is None:
        network = default_networks[encoder]
    ae = network(path)
    ae.train(train_data,
             epoch=epoch,
             anneal_rate=anneal_rate(epoch,max=max_temperature),
             max_temperature=max_temperature,
             # optimizer=Adam(0.003),
             batch_size=batch_size,
             test_data=test_data,
             report=False 
    )
    return ae

def grid_search(path, train=None, test=None):
    network = default_networks[encoder]
    names      = ['layer','dropout','N']
    parameters = [[4000],[0.4],[25]]
    best_error = float('inf')
    best_params = None
    best_ae     = None
    results = []
    print("Network: {}".format(network))
    try:
        import itertools
        for params in itertools.product(*parameters):
            params_dict = { k:v for k,v in zip(names,params) }
            print("Testing model with parameters={}".format(params_dict))
            ae = learn_model(path, train, test,
                             network=curry(network, parameters=params_dict))
            error = ae.autoencoder.evaluate(test,test,batch_size=100,verbose=0)
            results.append({'error':error,'epoch':epoch,'batch_size':batch_size,
                            **params_dict})
            print("Evaluation result for {} : error = {}".format(params_dict,error))
            print("Current results:\n{}".format(results),flush=True)
            if error < best_error:
                print("Found a better parameter {}: error:{} old-best:{}".format(
                    params_dict,error,best_error))
                best_params = params_dict
                best_error = error
                best_ae = ae
        print("Best parameter {}: error:{}".format(best_params,best_error))
    finally:
        print(results)
    best_ae.save()
    with open(best_ae.local("grid_search.log"), 'a') as f:
        import json
        f.write("\n")
        json.dump(results, f)
    return best_ae,best_params,best_error

def flip(bv1,bv2):
    "bv1,bv2: integer 1D vector, whose values are 0 or 1"
    iv1 = np.packbits(bv1,axis=-1)
    iv2 = np.packbits(bv2,axis=-1)
    return \
        np.unpackbits(np.bitwise_xor(iv1,iv2),axis=-1)[:, :bv1.shape[-1]]

def flips(bitnum,diffbit):
    # array = np.zeros(bitnum)
    def rec(start,diffbit,array):
        if diffbit > 0:
            for i in range(start,bitnum):
                this_array = np.copy(array)
                this_array[i] = 1
                for result in rec(i+1,diffbit-1,this_array):
                    yield result
        else:
            yield array
    return rec(0,diffbit,np.zeros(bitnum,dtype=np.int8))

def all_flips(bitnum,diffbit):
    size=1
    for i in range(bitnum-diffbit+1,bitnum+1):
        size *= i
    for i in range(1,diffbit+1):
        size /= i
    size = int(size)
    # print(size)
    array = np.zeros((size,bitnum),dtype=np.int8)
    import itertools
    for i,indices in enumerate(itertools.combinations(range(bitnum), diffbit)):
        array[i,indices] = 1
    return array

def augment_neighbors(ae, distance, bs1, bs2, threshold=0.,max_diff=None):
    bs1 = bs1.astype(np.int8)
    ys1 = ae.decode_binary(bs1,batch_size=6000)
    data_dim = np.prod(ys1.shape[1:])
    print("threshold {} corresponds to val_loss {}".format(threshold,threshold*data_dim))
    bitnum = bs1.shape[1]
    if max_diff is None:
        max_diff = bitnum-1
    final_bs1 = [bs1]
    final_bs2 = [bs2]
    failed_bv = []

    K.set_learning_phase(0)
    y_orig = K.placeholder(shape=ys1.shape)
    b = K.placeholder(shape=bs1.shape)
    z = tf.stack([b,1-b],axis=-1)
    y_flip = ae.decoder(z)
    ok = K.lesser_equal(distance(y_orig,y_flip),threshold)
    checker = K.function([y_orig,b],[ok])
    def check_ok(flipped_bs):
        return checker([ys1,flipped_bs])[0]
    try:
        last_skips = 0
        for diffbit in range(1,max_diff):
            some = False
            for bv in flips(bitnum,diffbit):
                if np.any([ np.all(np.greater_equal(bv,bv2)) for bv2 in failed_bv ]):
                    # print("previously seen with failure")
                    last_skips += 1
                    continue
                print(bv, {"blk": len(failed_bv), "skip":last_skips, "acc":len(final_bs1)})
                last_skips = 0
                flipped_bs = flip(bs1,[bv])
                oks = check_ok(flipped_bs)
                new_bs = flipped_bs[oks]
                ok_num = len(new_bs)
                if ok_num > 0:
                    some = True
                    final_bs1.append(new_bs)
                    # we do not enumerate destination states.
                    # because various states are applicable, single destination state is enough
                    final_bs2.append(bs2[oks])
                else:
                    failed_bv.append(bv)
            if not some:
                print("No more augmentation, stopped")
                break
    except KeyboardInterrupt:
        print("augmentation stopped")
    return np.concatenate(final_bs1,axis=0), np.concatenate(final_bs2,axis=0)

def bce(x,y):
    return K.mean(K.binary_crossentropy(x,y),axis=(1,2))

def dump_actions(ae,transitions,threshold=0.):
    orig, dest = transitions[0], transitions[1]
    orig_b = ae.encode_binary(orig,batch_size=6000).round().astype(int)
    dest_b = ae.encode_binary(dest,batch_size=6000).round().astype(int)
    actions = np.concatenate((orig_b,dest_b), axis=1)
    print(ae.local("actions.csv"))
    np.savetxt(ae.local("actions.csv"),actions,"%d")
    actions = np.concatenate(
        augment_neighbors(ae,bce,orig_b,dest_b,threshold=0.09), axis=1)
    print(ae.local("augmented.csv"))
    np.savetxt(ae.local("augmented.csv"),actions,"%d")

def dump(ae, train=None, test=None , transitions=None, **kwargs):
    if test is not None:
        plot_ae(ae,select(test,12),"autoencoding_test.png")
    plot_ae(ae,select(train,12),"autoencoding_train.png")
    if transitions is not None:
        dump_actions(ae,transitions)

def dump_all_actions(ae,configs,trans_fn):
    l = len(configs)
    batch = 10000
    loop = (l // batch) + 1
    try:
        print(ae.local("all_actions.csv"))
        with open(ae.local("all_actions.csv"), 'ab') as f:
            for begin in range(0,loop*batch,batch):
                end = begin + batch
                print((begin,end,len(configs)))
                transitions = trans_fn(configs[begin:end])
                orig, dest = transitions[0], transitions[1]
                orig_b = ae.encode_binary(orig,batch_size=6000).round().astype(int)
                dest_b = ae.encode_binary(dest,batch_size=6000).round().astype(int)
                actions = np.concatenate((orig_b,dest_b), axis=1)
                np.savetxt(f,actions,"%d")
    except KeyboardInterrupt:
        print("dump stopped")

################################################################

learn_flag = True

from plot import plot_ae

def select(data,num):
    return data[random.randint(0,data.shape[0],num)]

def run(learn,*args, **kwargs):
    if learn:
        ae, _, _ = grid_search(*args, **kwargs)
    else:
        ae = default_networks[encoder](args[0]).load()
        ae.summary()
    return ae

def mnist_puzzle():
    # N=81 too much
    # N=25
    import puzzles.mnist_puzzle as p
    configs = p.generate_configs(9)
    configs = np.array([ c for c in configs ])
    random.shuffle(configs)
    train_c = configs[:12000]
    test_c  = configs[12000:13000]
    train       = p.states(3,3,train_c)
    test        = p.states(3,3,test_c)
    print(len(configs),len(train),len(test))
    ae = run(learn_flag,"samples/mnist_puzzle33p_{}/".format(encoder), train, test)
    dump(ae, train,test)
    dump_all_actions(ae,configs,lambda configs: p.transitions(3,3,configs))

def random_mnist_puzzle():
    import puzzles.random_mnist_puzzle as p
    configs = p.generate_configs(9)
    configs = np.array([ c for c in configs ])
    random.shuffle(configs)
    train_c = configs[:12000]
    test_c  = configs[12000:13000]
    train       = p.states(3,3,train_c)
    test        = p.states(3,3,test_c)
    print(len(configs),len(train),len(test))
    ae = run(learn_flag,"samples/random_mnist_puzzle33p_{}/".format(encoder), train, test)
    dump(ae, train,test)
    dump_all_actions(ae,configs,lambda configs: p.transitions(3,3,configs))

def lenna_puzzle():
    import puzzles.lenna_puzzle as p
    configs = p.generate_configs(9)
    configs = np.array([ c for c in configs ])
    random.shuffle(configs)
    train_c = configs[:12000]
    test_c  = configs[12000:13000]
    train       = p.states(3,3,train_c)
    test        = p.states(3,3,test_c)
    print(len(configs),len(train),len(test))
    ae = run(learn_flag,"samples/lenna_puzzle33p_{}/".format(encoder), train, test)
    dump(ae, train,test)
    dump_all_actions(ae,configs,lambda configs: p.transitions(3,3,configs))

def mandrill_puzzle():
    import puzzles.mandrill_puzzle as p
    configs = p.generate_configs(9)
    configs = np.array([ c for c in configs ])
    random.shuffle(configs)
    train_c = configs[:12000]
    test_c  = configs[12000:13000]
    train       = p.states(3,3,train_c)
    test        = p.states(3,3,test_c)
    print(len(configs),len(train),len(test))
    ae = run(learn_flag,"samples/mandrill_puzzle33p_{}/".format(encoder), train, test)
    dump(ae, train,test)
    dump_all_actions(ae,configs,lambda configs: p.transitions(3,3,configs))

def spider_puzzle():
    import puzzles.spider_puzzle as p
    configs = p.generate_configs(9)
    configs = np.array([ c for c in configs ])
    random.shuffle(configs)
    train_c = configs[:12000]
    test_c  = configs[12000:13000]
    train       = p.states(3,3,train_c)
    test        = p.states(3,3,test_c)
    print(len(configs),len(train),len(test))
    ae = run(learn_flag,"samples/spider_puzzle33p_{}_long/", train, test)
    dump(ae, train,test)
    dump_all_actions(ae,configs,lambda configs: p.transitions(3,3,configs))

def digital_puzzle():
    import puzzles.digital_puzzle as p
    configs = p.generate_configs(9)
    configs = np.array([ c for c in configs ])
    random.shuffle(configs)
    train_c = configs[:12000]
    test_c  = configs[12000:13000]
    train       = p.states(3,3,train_c)
    test        = p.states(3,3,test_c)
    print(len(configs),len(train),len(test))
    ae = run(learn_flag,"samples/digital_puzzle33p_{}/".format(encoder), train, test)
    dump(ae, train,test)
    dump_all_actions(ae,configs,lambda configs: p.transitions(3,3,configs))

def hanoi():
    # 3000,0.4,N=64 worked best
    import puzzles.hanoi as p
    configs = p.generate_configs(6)
    configs = np.array([ c for c in configs ])
    random.shuffle(configs)
    states = p.states(6,configs)
    train       = states[:int(len(states)*(0.8))]
    test        = states[int(len(states)*(0.8)):]
    print(len(configs),len(train),len(test))
    ae = run(learn_flag,"samples/hanoi_{}/".format(encoder), train, test)
    dump(ae, train,test)
    dump_all_actions(ae,configs,lambda configs: p.transitions(6,configs))

def digital_lightsout():
    import puzzles.digital_lightsout as p
    configs = np.repeat(p.generate_configs(3),1,axis=0)
    configs = np.array([ c for c in configs ])
    random.shuffle(configs)
    train_c = configs[:int(len(configs)*(0.8))]
    test_c  = configs[int(len(configs)*(0.8)):]
    print(train_c)
    train       = p.states(3,train_c)
    test        = p.states(3,test_c)
    print(len(configs),len(train),len(test))
    ae = run(learn_flag,"samples/digital_lightsout_{}/".format(encoder), train, test)
    dump(ae, train,test)
    dump_all_actions(ae,configs,lambda configs: p.transitions(3,configs))

def mnist_counter():
    import puzzles.mnist_counter as p
    configs = np.repeat(p.generate_configs(10),10000,axis=0)
    states = p.states(10,configs)
    train       = states[:int(len(states)*(0.8))]
    test        = states[int(len(states)*(0.8)):]
    print(len(configs),len(train),len(test))
    ae = run(learn_flag,"samples/mnist_counter_{}/".format(encoder), train, test)
    dump(ae, train,test)
    dump_all_actions(ae,configs,lambda configs: p.transitions(10,configs))


def random_mnist_counter():
    import puzzles.random_mnist_counter as p
    configs = np.repeat(p.generate_configs(10),10000,axis=0)
    states = p.states(10,configs)
    train       = states[:int(len(states)*(0.8))]
    test        = states[int(len(states)*(0.8)):]
    print(len(configs),len(train),len(test))
    ae = run(learn_flag,"samples/random_mnist_counter_{}/".format(encoder), train, test)
    dump(ae, train,test)
    dump_all_actions(ae,configs,lambda configs: p.transitions(10,configs))

modes = {'learn':True,'dump':False}
if __name__ == '__main__':
    import sys
    if len(sys.argv) == 1:
        print({ k for k in default_networks})
        gs = globals()
        print({ k for k in gs if hasattr(gs[k], '__call__')})
        print({k for k in modes})
    else:
        encoder = sys.argv[1]
        if encoder not in default_networks:
            raise ValueError("invalid encoder!: {}".format(sys.argv))
        task = sys.argv[2]
        mode = sys.argv[3]
        if mode not in modes:
            raise ValueError("invalid mode!: {}".format(sys.argv))
        learn_flag = modes[mode]
        globals()[task]()
