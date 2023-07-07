case = 'january'
total_time_s = 0
for i in range(24):
    path = 'logs/{}/{}.log'.format(case, i)
    # path = 'slurm-71780476_' + str(i) + '.out'
    with open(path, 'r') as file:
        lines = file.readlines()

        if 'slurmstepd: error' in lines[-1]:
            print('Run', i, 'timeout')
            continue

        time = lines[-3].strip()
        time = time.split(' ')[1]
        total_time_s += float(time.split(',')[0])

        if 'successfully run' in lines[-4]:
            print('Run', i, 'sucess')
        else:
            print('Run', i, 'failure:', lines[-4].strip())

print('\nTotal time:', total_time_s)