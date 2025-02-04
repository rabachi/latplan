#!/bin/bash -x

make -j 1 -C lisp

set -e

trap exit SIGINT

ulimit -v 16000000000

export PYTHONUNBUFFERED=1


actionlearner4 (){
    lisp/domain-actionlearner4.bin $@ > $1/actionlearner4-$2-$3-$4-$5.pddl 2>$1/actionlearner4-$2-$3-$4-$5.err
}

export -f actionlearner4


base=samples-planning
# suffix="*"
suffix="puzzle_mnist_3_3_5000_None_None_None_False_ConcreteDetNormalizedLogitAddEffectTransitionAE_planning"

proj=$(date +%Y%m%d%H%M)al4-$base-$suffix
#common="jbsub -mem 32g -cores 16 -queue x86_6h -proj $proj"
common=""
actionlearner4 $base/*$suffix/ 3 actions_both+ids.csv 0 1.00

suffix="lightsout_digital_4_5000_None_None_None_False_ConcreteDetNormalizedLogitAddEffectTransitionAE_planning"

proj=$(date +%Y%m%d%H%M)al4-$base-$suffix
#common="jbsub -mem 32g -cores 16 -queue x86_6h -proj $proj"
common=""
actionlearner4 $base/*$suffix/ 3 actions_both+ids.csv 0 1.00

# base=samples-16
# suffix="*"

# proj=$(date +%Y%m%d%H%M)al4-$base-$suffix
# #common="jbsub -mem 32g -cores 16 -queue x86_6h -proj $proj"
# common=""
# parallel $common actionlearner4 ::: $base/*$suffix/ ::: 3 ::: actions_both+ids.csv ::: 0 ::: 1.00

