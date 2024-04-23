#!/bin/bash 

CTRL_DIR=$HOME/Documents/rad_gen/unit_tests/outputs/coffe/finfet_7nm_fabric_w_hbs/arch_out_COFFE_CONTROL_TEST
DUT_DIR=$HOME/Documents/rad_gen/unit_tests/outputs/coffe/finfet_7nm_fabric_w_hbs/arch_out_dir_stratix_iv_rrg




# Find relevant simulations to run
CKT_KEYS=( "sb" "cb" )
SP_SIMS=""
# ${DUT_DIR}
for DIR in ${CTRL_DIR} ${DUT_DIR}
do
    for CKT_KEY in "${CKT_KEYS[@]}"
    do
        SP_FILES=$(find ${DIR} -name "*${CKT_KEY}*" -type d -print0 | xargs -0 -I {} find {} -name "*.sp" -type f)
        SP_SIMS="${SP_SIMS} ${SP_FILES}"
    done
done


# touch sp_coffe_ckt_debug.log
for SP_SIM in $SP_SIMS
do
    # echo "Running ${SP_SIM}"
    echo $(date +"%Y-%m-%d %T")
    python3 rad_gen.py \
        -st ic_3d \
        -ds ${SP_SIM} \
        --input_config_path /fs1/eecg/vaughn/morestep/Documents/rad_gen/unit_tests/inputs/ic_3d/3D_ic_explore.yaml \
        | tee -a sp_coffe_ckt_debug.log
done


# python3 rad_gen.py \ 
#     -st \
#     ic_3d \
#     -ds \
#     ${CTRL_DIR}/
#      \
#     --input_config_path \
#     /fs1/eecg/vaughn/morestep/Documents/rad_gen/unit_tests/inputs/ic_3d/3D_ic_explore.yaml