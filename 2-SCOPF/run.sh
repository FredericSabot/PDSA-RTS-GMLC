case="january"
mkdir -p logs/$case

for i in {0..23}
do
    echo 'Running case' $case $i
    (time -p python3.9 PSCACOPF.py $i $case) > logs/$case/$i.log 2>&1
done
