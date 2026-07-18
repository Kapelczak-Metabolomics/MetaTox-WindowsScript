#!  /usr/bin/bash

#####################
### Help Function ###
#####################

help_msg() { 
    printf """
                     ===============
                    ||             ||
                    ||   MetaTox   ||
                    ||             ||
                     ===============

     ==================================================
    ||                                                 ||
    ||   https://github.com/alexisbourdais/MetaTox/    ||
    ||                                                 ||
     ==================================================

####################
### Requirements ###
####################

- Singularity

- Conda :
    wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
    chmod +x Miniconda3-latest-Linux-x86_64.sh
    ./Miniconda3-latest-Linux-x86_64.sh

- Some packages :
    sudo apt install -y zenity gawk dos2unix (zenity is optional, gawk and dos2unix are often already installed by default)

#####################
###   Input file  ###
#####################

-> 1st column : Molecule ID/Name
-> 2nd column : SMILES
-> Separator  : comma ','

Example:

Nicotine,CN1CCC[C@H]1c2cccnc2

##################
###    Usage   ### 
##################

* With zenity : ./MetaTox.sh

* To skip zenity : ./MetaTox.sh --input list_smile.txt [--option]
    
    REQUIRED parameter

        -i|--input   

    OPTIONAL parameter

        -o|--outdir     Name of the output directory [Results_prediction]

        -p|--predictor  To activate meta-Predictor [No]

        -b|--biotrans   Type of biotransformation to use with BioTransformer3:
                            [allHuman] : Predicts all possible metabolites from any applicable reaction(Oxidation, reduction, (de-)conjugation) at each step 
                            ecbased    : Prediction of promiscuous metabolism (e.g. glycerolipid metabolism). EC-based metabolism is also called Enzyme Commission based metabolism
                            cyp450     : CYP450 metabolism prediction 
                            phaseII    : Prediction of major conjugative reactions, including glucuronidation, sulfation, glycine transfer, N-acetyl transfer, and glutathione transfer, among others 
                            hgut       : Human gut microbial
                            superbio   : Runs a set number of transformation steps in a pre-defined order (e.g. deconjugation first, then Oxidation/reduction, etc.)
                            envimicro  : Environmental microbial

        -n|--nstep      The number of steps for the prediction by BioTransformer3 [default=1]

        -c|--cmode      CYP450 prediction Mode uses by BioTransformer: 
                            1  = CypReact+BioTransformer rules
                            2  = CyProduct only
                           [3] = CypReact+BioTransformer rules+CyProducts
                    
        -1|--phase1     Number of reaction cycles Phase 1 by SygMa [defaut=1]
        -2|--phase2     Number of reaction cycles Phase 2 by SygMa [defaut=1]

        -m|--metabo     Metabolism phase for GloryX : 
                          [phase_1_and_2]
                          phase_1
                          phase_2

        -k|--tmp        To keep intermediate files [No] (debugging)

"""
}

while [ $# -gt 0 ] ; do
    key="$1"
    case $key in
        -i|--input)
            input="$2"
            shift
            shift
            ;;
        -b|--biotrans)
            type="$2"
            shift
            shift
            ;;
        -n|--nstep)
            nstep="$2"
            shift
            shift
            ;;
        -c|--cmode)
            cmode="$2"
            shift
            shift
            ;;
        -1|--phase1)
            phase1="$2"
            shift
            shift
            ;;
        -2|--phase2)
            phase2="$2"
            shift
            shift
            ;;
        -p|--predictor)
            predictor_activate=true
            shift
            ;;
        -m|--metabo)
            phase_gloryx="$2"
            shift
            shift
            ;;
        -o|--outdir)
            outname="$2"
            shift
            shift
            ;;
        -k|--tmp)
            keep_tmp=true
            shift
            ;;
        *)
            help_msg
            exit 0                         
    esac
done

########################
### Spinner Function ###
########################

spinner() {
    local pid=$1
    local msg=$2
    local delay=0.1
    local spinstr='|/-\'
    local exit_code=0

    while kill -0 $pid 2>/dev/null; do
        local temp=${spinstr#?}
        printf "\r%s [%c]  " "$msg" "$spinstr"
        spinstr=$temp${spinstr%"$temp"}
        sleep $delay
    done

    wait $pid 2>/dev/null
    exit_code=$?
    if [ $exit_code -eq 0 ]; then
        printf "\r%s done ✓    \n" "$msg"
    else
        printf "\r%s failed ✗   \n" "$msg"
    fi
    return $exit_code
}

log_step_failure() {
    local label="$1"
    shift
    echo ""
    echo "ERROR: ${label}"
    for log_file in "$@"; do
        if [ -f "${log_file}" ]; then
            echo "----- ${log_file} (last 60 lines) -----"
            tail -n 60 "${log_file}"
        fi
    done
    echo ""
}

run_with_spinner() {
    local msg=$1
    local exit_code=0
    shift

    if [ "${METATOX_VERBOSE:-false}" = "true" ]; then
        echo ""
        echo ">>> ${msg}"
        "$@" || exit_code=$?
        echo ""
        return $exit_code
    fi

    ( "$@" ) >/dev/null 2>&1 &
    local pid=$!
    spinner $pid "$msg" || exit_code=$?
    return $exit_code
}

######################
### Work Directory ###
######################

work_dir="${PWD}"

# Nested Singularity inside Docker: never mount host /app over container /app.
unset APPTAINER_BINDPATH SINGULARITY_BINDPATH
export APPTAINER_NO_MOUNT="${APPTAINER_NO_MOUNT:-cwd,home,/etc/localtime}"
export SINGULARITY_NO_MOUNT="${SINGULARITY_NO_MOUNT:-cwd,home,/etc/localtime}"
SINGULARITY_COMMON_ARGS=(--no-mount cwd,home)

tmp="${work_dir}/tmp/"
if test -d $tmp; then
  rm -r $tmp
fi
mkdir $tmp

log="${work_dir}/log/"
if test -d $log; then
    :
else
    mkdir $log
fi

DirCondaEnv="${work_dir}/CondaEnv/"

DirScripts="${work_dir}/Scripts/"
Script_Metatox_Companion="${DirScripts}metatox_compagnion.py"

DirMetapred="${work_dir}/Meta-Predictor/"

##############
### Zenity ###
##############

if [ -z $input ]; then

    zenity --info --text "
    In silico prediction by :
    - Bio-transformer3
    - Sygma
    - GloryX
    - MetaTrans 
    - Meta-Predictor

    https://github.com/alexisbourdais/MetaTox/
    "

    input=$(zenity --file-selection --title="Select input file with each line = molecule,smiles")
    option_meta=$(zenity --forms --title="MetaTrans options" --text="Directly Validate to apply default values" --add-entry="Min length (SMILES) [defaut=5]" --add-entry="Max length (SMILES) [defaut=120]" --add-entry="Top results [defaut=5 : top 10]" --separator=",")
        min=$(echo "$option_meta" | cut -d "," -f1)
        max=$(echo "$option_meta" | cut -d "," -f2)
        beam=$(echo "$option_meta" | cut -d "," -f3)

    option_sygma=$(zenity --forms --title="Sygma options" --text="Directly Validate to apply default values" --add-entry="Number of reaction cycles Phase 1 [defaut=1]" --add-entry="Number of reaction cycles Phase 2 [defaut=1]" --separator=",")
        phase1=$(echo "$option_sygma" | cut -d "," -f1)
        phase2=$(echo "$option_sygma" | cut -d "," -f2)

    type=$(zenity --list --title="Biotransformer 3 model" --text="Choose the type of biotransformation to use with Biotransformer3" --column="Type" --column="Description" \
    allHuman "Predicts all possible metabolites from any applicable reaction(Oxidation, reduction, (de-)conjugation) at each step" ecbased "Prediction of promiscuous metabolism (e.g. glycerolipid metabolism). EC-based metabolism is also called Enzyme Commission based metabolism" cyp450 "CYP450 metabolism prediction" phaseII "Prediction of major conjugative reactions, including glucuronidation, sulfation, glycine transfer, N-acetyl transfer, and glutathione transfer, among others" hgut "Human gut microbial" superbio "Runs a set number of transformation steps in a pre-defined order (e.g. deconjugation first, then Oxidation/reduction, etc.)" envimicro "Environmental microbial" )
    
    option_biotrans=$(zenity --forms --title="Biotransformer options" --text="Directly Validate to apply default values" --add-entry="The number of steps for the prediction [default=1]" --add-entry="CYP450 prediction Mode: 1=CypReact+BioTransformer rules; 2=CyProduct only; 3=CypReact+BioTransformer rules+CyProducts [Default=3]" --separator=",")
        nstep=$(echo "$option_biotrans" | cut -d "," -f1)
        cmode=$(echo "$option_biotrans" | cut -d "," -f2)

    zenity --question --title="Meta-Predictor Activation" --text="Do you want to activate Meta-Predictor ?"
    predictor_activate_answer=$?
    if [ $predictor_activate_answer -eq 0 ]; then
	    predictor_activate=true
    else [ $predictor_activate_answer -eq 1 ]
    	predictor_activate=false
    fi

    phase_gloryx=$(zenity --list --title="Metabolism phase for GloryX" --text="Choose the metabolism phase to use with GloryX" --column="Phase" --column="Description" \
        phase_1_and_2 "Phase 1 and phase 2 metabolism" phase_1 "Phase 1 metabolism" phase_2 "Phase 2 metabolism")

fi

#######################
### Default Options ###
#######################

###Outdir
if [ -z $outname ]; then
	outname="Results_Prediction"
fi

DirOutput="${work_dir}/${outname}/"

if test -d $DirOutput; then
    :
else
    mkdir $DirOutput
fi

###Bio-Transformer options
#Default Mode
biotrans_valid_mode=("allHuman" "ecbased" "cyp450" "phaseII" "hgut" "superbio" "envimicro")

if [ -z "$type" ] || [[ ! " ${biotrans_valid_mode[@]} " =~ " ${type} " ]]; then
	type="allHuman"
fi

#Default nsteps
if [ -z $nstep ] || [[ ! $nstep = +([0-9]) ]]; then
	nstep="1"
fi

#Default cmode
if [ -z "$cmode" ] || [[ ! $cmode =~ ^[1-3]$ ]]; then
	cmode="3"
fi

###Meta-Trans options
#Default Beam
if [ -z $BEAM ] || [[ ! $BEAM = +([0-9]) ]]; then
	BEAM=5
fi

#Default min
if [ -z $MIN ] || [[ ! $MIN = +([0-9]) ]]; then
	MIN=5 
fi

#Default Max
if [ -z $MAX ] || [[ ! $MAX = +([0-9]) ]]; then
	MAX=120
fi

###Sygma options
#Default phase1
if [ -z $phase1 ] || [[ ! $phase1 = +([0-9]) ]]; then
	phase1=1
fi

#Default phase2
if [ -z $phase2 ] || [[ ! $phase2 = +([0-9]) ]]; then
	phase2=1 
fi

###Meta-Predictor option
if [ -z $predictor_activate ]; then
	predictor_activate=false
fi

###GloryX option
#Metabolism phase for gloryX
if [ -z "$phase_gloryx" ] || ([ "$phase_gloryx" != "phase_1" ] && [ "$phase_gloryx" != "phase_2" ] && [ "$phase_gloryx" != "phase_1_and_2" ]); then
	phase_gloryx="phase_1_and_2"
fi

###Keep intermediate files
if [ -z $keep_tmp ]; then
	keep_tmp=false
fi

echo "
                 ===============
                ||             ||
                ||   MetaTox   ||
                ||             ||
                 ===============

 ==================================================
||                                                 ||
||   https://github.com/alexisbourdais/MetaTox/    ||
||                                                 ||
 ==================================================

    - BioTransformer bio-reaction : $type
    - BioTransformer cycle number : $nstep
    - Biotransformer CYP450 prediction Mode : $cmode

    - SygMa Phase 1 cycle number : $phase1
    - SygMa Phase 2 cycle number : $phase2

    - GloryX metabolism phase : $phase_gloryx

    - Meta-Predictor activation : $predictor_activate
"

###############
###  Input  ###
###############

if command -v file >/dev/null 2>&1; then
    file "$input" | grep -q CRLF && dos2unix "$input"
else
    dos2unix -q "$input" 2>/dev/null || true
fi

declare -a tab_molecule
declare -a tab_smiles

while read a
do
    Molecule=$(echo $a | cut -d\, -f1)
    Smiles=$(echo $a | cut -d\, -f2)
    tab_smiles[${#tab_smiles[@]}]=${Smiles}
    tab_molecule[${#tab_molecule[@]}]=${Molecule}
done < "$input"

path_input="$(realpath ${input})"

######################
### META-PREDICTOR ###
######################

metapredictor_job() {

    ### Conda Environment ###
    eval "$(conda shell.bash hook)"

    if conda info --envs | grep -q metapredictor; then 
        :
    else 
        echo "Installation of metapredictor environment :"
        conda env create --name metapredictor --file ${DirCondaEnv}metapred_environment.yml
    fi

    conda activate metapredictor
    cd ${DirMetapred}

    python prepare_input_file.py -input_file ${path_input} -output_file processed_data.txt

    # --- Lancement avec capture du code retour ---
    bash predict-top15.sh processed_data.txt ./prediction "${path_input}" \
        > "${log}Metapredictor_log.txt" 2>&1
    status=$?
    if [ $status -ne 0 ]; then
        echo "predict-top15.sh failed with exit code $status" >> "${log}Metapredictor_log.txt"
        return $status
    fi

    conda deactivate

    ### Mv results and remove temp files
    mv prediction/predict.csv ${tmp}Prediction_Metapred.csv
    rm -r prediction/* Figures/* processed_data.txt

    # Separation of results into separate files for each molecule
    cd ${tmp}
    pat="^Name"

    while read a; do
        if [[ $a =~ $pat ]]; then
            :
        else
            MoleculeID=$(echo $a | cut -d, -f1)
            SmileMetabo=$(echo $a | cut -d, -f3)
            read -ra tab_metabo <<< "$SmileMetabo"
            for i in ${tab_metabo[@]}; do
                echo "${i}" >> "${MoleculeID}_Metapred.csv"
            done
        fi
    done < "Prediction_Metapred.csv"
    rm Prediction_Metapred.csv

    cd $work_dir
}

if ${predictor_activate}; then

    echo "

    *** Process of $input ***

    "
    run_with_spinner "MetaPredictor ..." metapredictor_job
fi

#################
### Main loop ###
#################

step_failures=0

for indice in ${!tab_molecule[@]}
do

    echo "

    *** Process of ${tab_molecule[${indice}]} ***

    "

    results_file="${DirOutput}${tab_molecule[${indice}]}_CompileResults.tsv"
    results_figure="${DirOutput}${tab_molecule[${indice}]}_figures/"
    mkdir -p ${results_figure}

    #########################
    ### BIOTRANSFORMERS 3 ###
    #########################

    biotransformer_job () {
        set -e
        set -o pipefail
        local mol="${tab_molecule[${indice}]}"

        singularity exec "${SINGULARITY_COMMON_ARGS[@]}" -B "${tmp}:/tmp" \
        https://depot.galaxyproject.org/singularity/biotransformer:3.0.20230403--hdfd78af_0 biotransformer \
        -b "${type}" \
        -k "pred" \
        -cm "${cmode}" \
        -s "${nstep}" \
        -ismi "${tab_smiles[${indice}]}" \
        -ocsv "/tmp/${mol}_Biotransformer3_v1.csv" 2>&1 | tee -a "${log}${mol}_Biotransformer3_log.txt"

        singularity exec "${SINGULARITY_COMMON_ARGS[@]}" -B "${tmp}:/tmp" library://abourdais/default/rdkit csvformat \
        -D ";" "/tmp/${mol}_Biotransformer3_v1.csv" \
        | gawk -v RS='"' 'NR % 2 == 0 { gsub(/\n/, "") } { printf("%s%s", $0, RT) }' \
        > "${tmp}${mol}_Biotransformer3.csv"

        rm "${tmp}${mol}_Biotransformer3_v1.csv"
    }

    if ! run_with_spinner "Biotransformer3 ..." biotransformer_job; then
        step_failures=$((step_failures + 1))
        log_step_failure "Biotransformer3 failed" \
            "${log}${tab_molecule[${indice}]}_Biotransformer3_log.txt"
    fi

    ##################
    ###    SygMa   ###
    ##################

    sygma_job () {
        set -e
        singularity run "${SINGULARITY_COMMON_ARGS[@]}" docker://3dechem/sygma ${tab_smiles[${indice}]} \
        -1 $phase1 \
        -2 $phase2 \
        >> "${tmp}${tab_molecule[${indice}]}_Sygma.sdf" 2>> "${log}${tab_molecule[${indice}]}_Sygma_log.txt"
    }

    if ! run_with_spinner "Sygma ..." sygma_job; then
        step_failures=$((step_failures + 1))
        log_step_failure "SygMa failed" "${log}${tab_molecule[${indice}]}_Sygma_log.txt"
    fi

    ###################
    ###    GloryX   ### !!! TO DO !!!
    ###################

    gloryx_job () {
        set -e
        local mol="${tab_molecule[${indice}]}"
        singularity run "${SINGULARITY_COMMON_ARGS[@]}" -B "${tmp}:/tmp" library://abourdais/default/gloryx_api \
        --phase $phase_gloryx \
        --smile ${tab_smiles[${indice}]} \
        --output "/tmp/${mol}_Gloryx.csv" \
        > "${log}${mol}_Gloryx_log.txt" 2>&1
    }

    if ! run_with_spinner "GloryX ..." gloryx_job; then
        step_failures=$((step_failures + 1))
        log_step_failure "GLORYx failed" "${log}${tab_molecule[${indice}]}_Gloryx_log.txt"
    fi

    ##################
    ### META-TRANS ###
    ##################

    metatrans_job () {
        set -e
        local mol="${tab_molecule[${indice}]}"
        singularity run "${SINGULARITY_COMMON_ARGS[@]}" --containall -B "${tmp}:/tmp" --writable-tmpfs library://abourdais/default/metatrans \
        -n ${mol} \
        -s ${tab_smiles[${indice}]} \
        -r /tmp/${mol}_MetaTrans.csv \
        -l /tmp/${mol}_MetaTrans_log.txt

        mv "${tmp}${mol}_MetaTrans_log.txt" "${log}"
        rm -rf "${tmp}Predictions"
    }

    if ! run_with_spinner "MetaTrans ..." metatrans_job; then
        step_failures=$((step_failures + 1))
        log_step_failure "MetaTrans failed" "${log}${tab_molecule[${indice}]}_MetaTrans_log.txt"
    fi

    ###################
    ### Compilation ###
    ###################

    compilation_job () {
        set -e
        if [ "${METATOX_NATIVE_COMPILE:-false}" = "true" ]; then
            python3 ${Script_Metatox_Companion} \
                --biotrans "${tmp}${tab_molecule[${indice}]}_Biotransformer3.csv" \
                --sygma "${tmp}${tab_molecule[${indice}]}_Sygma.sdf" \
                --metapred "${tmp}${tab_molecule[${indice}]}_Metapred.csv" \
                --metatrans "${tmp}${tab_molecule[${indice}]}_MetaTrans.csv" \
                --gloryx "${tmp}${tab_molecule[${indice}]}_Gloryx.csv" \
                --output "${results_file}" \
                --figure "${tmp}${tab_molecule[${indice}]}_ListeSmile.txt" \
                --dirfig "${results_figure}" \
                > "${log}${tab_molecule[${indice}]}_Compagnion_log.txt" 2>&1
        else
            singularity exec "${SINGULARITY_COMMON_ARGS[@]}" -B "${tmp}:/tmp" -B "${DirScripts}:/scripts" library://abourdais/default/rdkit python /scripts/metatox_compagnion.py \
                --biotrans "/tmp/${tab_molecule[${indice}]}_Biotransformer3.csv" \
                --sygma "/tmp/${tab_molecule[${indice}]}_Sygma.sdf" \
                --metapred "/tmp/${tab_molecule[${indice}]}_Metapred.csv" \
                --metatrans "/tmp/${tab_molecule[${indice}]}_MetaTrans.csv" \
                --gloryx "/tmp/${tab_molecule[${indice}]}_Gloryx.csv" \
                --output "${results_file}" \
                --figure "/tmp/${tab_molecule[${indice}]}_ListeSmile.txt" \
                --dirfig "${results_figure}" \
                > "${log}${tab_molecule[${indice}]}_Compagnion_log.txt" 2>&1
        fi

        rm ${tmp}${tab_molecule[${indice}]}_ListeSmile.txt
    }

    if ! run_with_spinner "Compilation ..." compilation_job; then
        step_failures=$((step_failures + 1))
        log_step_failure "Compilation failed" "${log}${tab_molecule[${indice}]}_Compagnion_log.txt"
    fi

done

if ${keep_tmp}; then
    :
else
    rm -r $tmp
fi

echo "
Recording results in : ${DirOutput}

Execution completed !
"

if [ "${step_failures:-0}" -gt 0 ]; then
    echo "WARNING: ${step_failures} pipeline step(s) failed. Check /app/log for details."
    exit 1
fi
