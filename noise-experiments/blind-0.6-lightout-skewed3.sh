#!/bin/bash
./plan_noise.py blind 0.6 'run_lightsout3 ( "samples/digital_lightsout_skewed3_fc"       ,"fc", import_module("puzzles.digital_lightsout_skewed"        ) )' |& tee $(dirname $0)/blind-0.6-lightout-skewed3.log
