

################################################################

def dijkstra(init_c,length,successor_fn,include_nonleaf=False):
    import queue
    open_list = queue.PriorityQueue()
    close_list = {}

    t = init_c
    open_list.put((0, t))
    close_list[t] = {"g":0, "open":True, "reopen":False, "parent":None}

    expanded = 0
    g_max = -1

    while not open_list.empty():
        expanded += 1
        g, current = open_list.get()
        if close_list[current]["open"] == False:
            continue
        close_list[current]["open"]=False

        if g > length:
            print("explored all nodes with g < {}".format(length))
            return
        if g == length:
            yield current, close_list
        if g < length and include_nonleaf: # yield all nodes below the specified depth
            yield current, close_list
        if g > g_max:
            print("new g",g,"expanded",expanded)
            g_max = g

        g_new = g+1

        for succ in successor_fn(current):
            if succ in close_list:
                node = close_list[succ]
                if g_new < node["g"]: # reopen
                    node["g"]    = g_new
                    node["open"] = True
                    node["reopen"] = True
                    node["parent"] = current
                    open_list.put((g_new,succ))
            else:
                close_list[succ] = {"g":g_new, "open":True, "reopen":False, "parent":current}
                open_list.put((g_new,succ))
    print("open list exhausted")
    return



def random_walk(init_c,length,successor_fn):
    print(".",end="")
    while True:
        result = random_walk_rec(init_c, [init_c], length, successor_fn)
        print()
        if result is None:
            continue
        else:
            return result

def random_walk_rec(current, trace, length, successor_fn):
    import numpy.random as random
    if length == 0:
        return current
    else:
        sucs = successor_fn(current)
        first = random.randint(len(sucs))
        now = first

        while True:
            suc = sucs[now]
            try:
                assert not np.any([np.all(np.equal(suc, t)) for t in trace])
                result = random_walk_rec(suc, [*trace, suc], length-1, successor_fn)
                assert result is not None
                return result
            except AssertionError:
                now = (now+1)%len(sucs)
                if now == first:
                    print("B",end="")
                    return None
                else:
                    continue
