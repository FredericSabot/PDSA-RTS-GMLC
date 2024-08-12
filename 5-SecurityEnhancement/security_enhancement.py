from lxml import etree
from sklearn.tree import DecisionTreeClassifier
from sklearn import linear_model
import sklearn.preprocessing
import sklearn.decomposition
import sklearn.svm
import sklearn.inspection
import sklearn.model_selection
import sklearn.feature_selection
import sklearn.pipeline
from sklearn import tree
from sklearn.base import clone
import imblearn.under_sampling
import pypowsybl as pp
import numpy as np
import matplotlib.pyplot as plt
import glob
import os
import pickle
from pathlib import Path

DYNAWO_NAMESPACE = 'http://www.rte-france.com/dynawo'
NETWORK_NAME = 'RTS'

feature_names = []

# Due to variance, the most critical contingencies in the final xml might slightly difer from
# the ones for which MIN_NUMBER_STATIC_SEED_CRITICAL_CONTINGENCY have been run. The latter
# are thus copied below from the end of the log0.log file
critical_contingency_list = [
    'A34_end1_DELAYED',
    'CA-1_end2_DELAYED',
    'A25-1_end2_DELAYED',
    'A31-1_end2_DELAYED',
    'A25-1_end1-BREAKER_end1-A25-2',
    'CA-1_end2-BREAKER_end2-A34',
    'A23_end2-BREAKER_end2-A28',
    'A34_end1-BREAKER_end1-A25-1',
    'A34_end1-BREAKER_end1-CA-1',
    'A25-1_end2-BREAKER_end2-A25-2']

def get_features(path):
    global feature_names
    par_root = etree.parse('../3-DynData/{}.par'.format(NETWORK_NAME)).getroot()
    n = pp.network.load(path)

    features = np.array(n.get_generators().p) * -1  # Sign change from receptor convention
    features = np.concatenate([features, np.array(n.get_generators().q) * -1])
    features = np.concatenate([features, np.array(n.get_buses().v_mag)])
    # features = np.concatenate([features, np.array(n.get_buses().v_angle)])
    features = np.concatenate([features, np.array(n.get_lines().p1)])
    features = np.concatenate([features, np.array(n.get_lines().p2)])
    np.nan_to_num(features, copy=False, nan=0)  # Set NaN values (disconnected generator outputs) to 0

    feature_names = ['P_' + index for index in n.get_generators().index]
    feature_names += ['Q_' + index for index in n.get_generators().index]
    feature_names += ['Vmag_' + index for index in n.get_buses().index]
    # feature_names += ['Vangle_' + index for index in n.get_buses().index]
    feature_names += ['P1_' + index for index in n.get_lines().index]
    feature_names += ['Q1_' + index for index in n.get_lines().index]

    total_thermal = 0
    total_hydro = 0
    total_solar = 0
    total_wind = 0
    total_inertia = 0
    gens = n.get_generators()
    reserves = 0

    for gen_id in gens.index:
        if not gens.at[gen_id, 'connected']:
            continue

    for gen_id in gens.index:
        if np.isnan(gens.at[gen_id, 'p']):
            continue

        p = -gens.at[gen_id, 'p']
        p_max = gens.at[gen_id, 'max_p']
        reserves += (p_max - p)

        if gens.at[gen_id, 'energy_source'] == 'THERMAL':
            total_thermal += -gens.at[gen_id, 'p']
        elif gens.at[gen_id, 'energy_source'] == 'HYDRO':
            total_hydro += -gens.at[gen_id, 'p']
        elif gens.at[gen_id, 'energy_source'] == 'SOLAR':
            total_solar += -gens.at[gen_id, 'p']
        elif gens.at[gen_id, 'energy_source'] == 'WIND':
            total_wind += -gens.at[gen_id, 'p']

        if gens.at[gen_id, 'energy_source'] not in ['SOLAR', 'WIND']:
            par_set = par_root.find("{{{}}}set[@id='{}']".format(DYNAWO_NAMESPACE, gen_id))
            if par_set is None:
                raise ValueError(path, gen_id, 'parameters not found')
            Snom = float(par_set.find("{{{}}}par[@name='generator_SNom']".format(DYNAWO_NAMESPACE)).get('value'))
            inertia = float(par_set.find("{{{}}}par[@name='generator_H']".format(DYNAWO_NAMESPACE)).get('value'))
            total_inertia += Snom * inertia

    loads = np.array(n.get_loads().p)
    np.nan_to_num(loads, copy=False, nan=0)
    total_load = sum(loads)
    ibg_penetration = (total_solar + total_wind) / total_load * 100

    features = np.concatenate([features, np.array([total_thermal, total_hydro, total_solar, total_wind, ibg_penetration, total_load, total_inertia])])
    feature_names += ['Total_thermal', 'Total_hydro', 'Total_solar', 'Total_wind', 'IBG penetration (%)', 'Total_load', 'Total_inertia']

    return features


def print_feature_importance(pipe: sklearn.pipeline.Pipeline, feature_names):
    model = pipe[-1]
    if isinstance(model, DecisionTreeClassifier):
        coefs = model.feature_importances_
    elif isinstance(model, sklearn.svm.LinearSVC) or isinstance(model, linear_model.RidgeClassifier):
        coefs = model.coef_[0]
    else:
        raise NotImplementedError(model, "not considered")
        importance = sklearn.inspection.permutation_importance(pipe, X_test, y_test)
        coefs = importance.importances_mean
        print(coefs.shape)

    feature_weigths = {feature_names[i]: coefs[i] for i in range(len(coefs))}
    feature_weigths = {key: value for key, value in sorted(feature_weigths.items(), key = lambda item:abs(item[1]), reverse=True)}

    i = 0
    for feature in feature_weigths:
        if feature_weigths[feature] != 0:
            print(feature, '{:.3f}'.format(feature_weigths[feature]))
        i += 1
        if i > 10:
            break
    print()


def custom_feature_selection(model, X, y):
    """
    Custom feature selection based on sklearn.feature_selection.SequentialFeatureSelector that also
    outputs features close to best score at each iteration
    """
    cloned_estimator = clone(model)
    n_features = X.shape[1]

    current_mask = np.zeros(shape=n_features, dtype=bool)  # Start with 0 features

    old_score = 0
    feature_scores = []
    for _ in range(2):
        candidate_feature_indices = np.flatnonzero(~current_mask)
        scores = {}
        for feature_idx in candidate_feature_indices:
            candidate_mask = current_mask.copy()
            candidate_mask[feature_idx] = True
            X_new = X[:, candidate_mask]
            scores[feature_idx] = sklearn.model_selection.cross_val_score(cloned_estimator, X_new, y,).mean()
        new_feature_idx = max(scores, key=lambda feature_idx: scores[feature_idx])
        new_score = scores[new_feature_idx]

        if (new_score - old_score) <= 1e-3:
            break

        scores = {key: value for key, value in sorted(scores.items(), key=lambda item: item[1], reverse=True)}

        old_score = new_score
        current_mask[new_feature_idx] = True
        feature_scores.append(scores)

    return current_mask, feature_scores


if __name__ == '__main__':
    feature_path = 'features.pickle'
    static_files = glob.glob('../2-SCOPF/d-Final-dispatch/year/*.iidm')
    if os.path.exists(feature_path):
        with open(feature_path, 'rb') as file:
            features = pickle.load(file)
        get_features(static_files[0])  # Run at least once to get feature names
    else:
        features = {}
        for i, static_file in enumerate(static_files):
            print('Loading sample', i, 'out of', len(static_files), end='\r')
            id = os.path.basename(static_file)
            id = os.path.splitext(id)[0]  # Remove extension
            features[id] = get_features(static_file)
        print()
        with open(feature_path, 'wb') as file:
            pickle.dump(features, file, protocol=pickle.HIGHEST_PROTOCOL)

    # Remove unwanted features
    indices = []
    for i, name in enumerate(feature_names):
        # if 'P1_' not in name and 'Q1_' not in name:
        if 'Q_' in name or 'Q1_' in name or 'Vmag' in name: # or 'P1' in name:
            indices.append(i)
    for key, feature in features.items():
        features[key] = np.delete(feature, indices)
    for index in reversed(indices):
        del feature_names[index]


    root = etree.parse('../4-PDSA/AnalysisOutput.xml').getroot()
    worst_contingencies = sorted(root, key=lambda x : float(x.get('cost')), reverse=True)

    critical_contingency_indices = []
    for i in range(len(worst_contingencies)):
        if worst_contingencies[i].get('id') in critical_contingency_list:
            critical_contingency_indices.append(i)

    for contingency_index in range(10):
        critical_contingency = worst_contingencies[contingency_index]
        print("\n\n\nContingency", critical_contingency.get('id'))

        samples = []
        labels = []
        colors = []

        for j, sample in enumerate(critical_contingency):
            samples.append(features[sample.get('static_id')])
            labels.append(float(sample.get('mean_load_shed')) > 0)

            trip_0 = sample.get('trip_0')
            trip_1 = sample.get('trip_1')
            trip_2 = sample.get('trip_2')
            if trip_0 is None or 'RTPV' in trip_0:
                trip_0 = ''
            if trip_1 is None or 'RTPV' in trip_1:
                trip_1 = ''
            if trip_2 is None or 'RTPV' in trip_2:
                trip_2 = ''
            load_shedding = float(sample.get('mean_load_shed'))

            # if label > 0:
            #     colors.append('red')
            # else:
            #     colors.append('green')
            if load_shedding > 20:
                colors.append('red')
            elif load_shedding > 0:
                colors.append('orange')
            elif trip_0 != '' or trip_1 != '' or trip_2 != '':
                colors.append('yellow')
            else:
                colors.append('green')

        try:
            X_train, X_test, y_train, y_test = sklearn.model_selection.train_test_split(samples, labels, random_state=42)
            X_train, y_train = imblearn.under_sampling.RandomUnderSampler(random_state=42).fit_resample(X_train, y_train)
            X_test, y_test = imblearn.under_sampling.RandomUnderSampler(random_state=42).fit_resample(X_test, y_test)
        except ValueError:
            continue
        print(len(y_train))
        if len(y_train) < 30:
            print('No enough data to train (most likely not enough unsecure cases)')
            continue

        """ Path("trees").mkdir(exist_ok=True)
        # Decision tree
        model = DecisionTreeClassifier(max_depth=3, min_impurity_decrease=0.01)
        pipe = sklearn.pipeline.Pipeline([
            ('model', model)
        ])
        print('DT precision', pipe.fit(X_train, y_train).score(X_test, y_test))
        print('DT training precision', pipe.score(X_train, y_train))
        print_feature_importance(pipe, feature_names)
        dt = pipe['model']
        tree.plot_tree(dt, feature_names=pipe[:-1].get_feature_names_out(feature_names), max_depth=3)
        plt.savefig('trees/{}_tree_{}.pdf'.format(contingency_index, critical_contingency.get('id')))
        plt.close()


        # Decision tree with feature selection
        model = DecisionTreeClassifier(min_impurity_decrease=0.01)
        pipe = sklearn.pipeline.Pipeline([
            ('feature_selection', sklearn.feature_selection.SequentialFeatureSelector(model, n_features_to_select=5)),
            ('model', model)
        ])
        print('DT precision (selected features)', pipe.fit(X_train, y_train).score(X_test, y_test))
        print('DT training precision (selected features)', pipe.score(X_train, y_train))
        print_feature_importance(pipe, pipe[:-1].get_feature_names_out(feature_names))
        dt = pipe['model']
        tree.plot_tree(dt, feature_names=pipe[:-1].get_feature_names_out(feature_names), max_depth=3)
        plt.savefig('trees/{}_tree_{}_features.pdf'.format(contingency_index, critical_contingency.get('id')))
        plt.close() """


        """ # SVM
        pipe = sklearn.pipeline.Pipeline([
            ('scaler', sklearn.preprocessing.StandardScaler()),
            ('model', sklearn.svm.LinearSVC(penalty="l1", loss="squared_hinge", dual=False, C=1))
        ])
        print('SVM precision', pipe.fit(X_train, y_train).score(X_test, y_test))
        print('SVM training precision', pipe.score(X_train, y_train))
        print_feature_importance(pipe, feature_names) """

        #pca = sklearn.decomposition.PCA(n_components=None)
        #pca.fit(samples)
        #samples = pca.transform(samples)


        """ # SVM with feature selection
        model = sklearn.svm.LinearSVC(penalty="l1", loss="squared_hinge", dual=False, C=1)
        pipe = sklearn.pipeline.Pipeline([
            ('scaler', sklearn.preprocessing.StandardScaler()),
            ('feature_selection', sklearn.feature_selection.SequentialFeatureSelector(model, n_features_to_select=5)),
            ('model', model)
        ])
        print('SVM precision (selected features)', pipe.fit(X_train, y_train).score(X_test, y_test))
        print('SVM training precision (selected features)', pipe.score(X_train, y_train))
        print_feature_importance(pipe, pipe[:-1].get_feature_names_out(feature_names)) """


        """ # Ridge classifier with feature selection
        model = linear_model.RidgeClassifier(alpha=100)
        # alphas = np.logspace(-10, 10, 21)
        # reg = linear_model.RidgeClassifierCV(alphas)
        pipe = sklearn.pipeline.Pipeline([
            ('scaler', sklearn.preprocessing.StandardScaler()),
            ('feature_selection', sklearn.feature_selection.SequentialFeatureSelector(model, n_features_to_select=5)),
            ('model', model)
        ])
        print('Ridge precision (selected features)', pipe.fit(X_train, y_train).score(X_test, y_test))
        print('Ridge training precision (selected features)', pipe.score(X_train, y_train))
        print_feature_importance(pipe, pipe[:-1].get_feature_names_out(feature_names)) """

        # SVM with custom feature selection
        model = sklearn.svm.LinearSVC(penalty="l2", loss="squared_hinge", dual=False, C=1)
        scaler = sklearn.preprocessing.StandardScaler().fit(X_train)
        X_train = sklearn.preprocessing.StandardScaler().fit_transform(X_train)
        X_test = sklearn.preprocessing.StandardScaler().fit_transform(X_test)
        feature_mask, feature_scores_list = custom_feature_selection(model, X_train, y_train)
        X_train_selected = X_train[:, feature_mask]
        X_test_selected = X_test[:, feature_mask]
        model.fit(X_train_selected, y_train)
        print('SVM precision (selected features)', model.score(X_test_selected, y_test))
        print('SVM training precision (selected features)', model.score(X_train_selected, y_train))


        old_score = 0
        best_feature_ids = []
        for feature_scores in feature_scores_list:
            first_features = iter(feature_scores)
            best_feature_ids.append(next(first_features))
            # best_feature_ids.append(next(first_features))
            for i, feature_id in enumerate(feature_scores.keys()):
                if feature_scores[feature_id] - old_score < 1e-3:
                    # print("No other relevant features\n")
                    break
                print("{} {:.1f}".format(feature_names[feature_id], (feature_scores[feature_id] - old_score)*100))
                if i > 10:
                    print()
                    break
            for score in feature_scores:
                old_score = feature_scores[score]
                break

        best_feature_ids = best_feature_ids[:2]  # 2D plot max
        samples = np.array(samples)[:, best_feature_ids]

        feature_names = np.array(feature_names)
        plt.scatter(x=samples[:, 0], y=samples[:, 1], c=colors)
        plt.xlabel(feature_names[best_feature_ids[0]])
        plt.ylabel(feature_names[best_feature_ids[1]])
        plt.title('Contingency ' + critical_contingency.get('id'))

        model = sklearn.svm.LinearSVC(penalty="l1", loss="squared_hinge", dual=False, C=1).fit(X_train[:, best_feature_ids], y_train)

        # coefs = (model.coef_ / scaler.scale_[best_feature_ids])[0]
        # b = -model.intercept_[0] + sum(scaler.mean_[best_feature_ids] / scaler.scale_[best_feature_ids])
        # ax = ' + '.join(['{} * {}'.format(coefs[i], feature_names[best_feature_ids][i]) for i in range(len(np.flatnonzero(feature_mask)))])
        # ax = ' + '.join(['{} * {}'.format(coefs[i], feature_names[best_feature_ids][i]) for i in range(2)])

        axes = plt.gca()
        x_vals = np.array(axes.get_xlim())
        # y_vals = (b - coefs[0] * x_vals) / coefs[1]
        y_vals = scaler.mean_[best_feature_ids[1]] + scaler.scale_[best_feature_ids[1]] / model.coef_[0][1] * \
                    (-model.intercept_[0] - model.coef_[0][0] * (x_vals - scaler.mean_[best_feature_ids[0]]) / scaler.scale_[best_feature_ids[0]])

        plt.plot(x_vals, y_vals, '--')
        plt.ylim([min(samples[:, 1]), max(samples[:, 1])])


        x_reduced = (x_vals - scaler.mean_[best_feature_ids[0]]) / scaler.scale_[best_feature_ids[0]]
        y_reduced = (y_vals - scaler.mean_[best_feature_ids[1]]) / scaler.scale_[best_feature_ids[1]]
        # model.coef_[0][0] * x_reduced + model.coef_[0][1] * y_reduced + model.intercept_ = 0
        a = model.coef_[0][0] / scaler.scale_[best_feature_ids[0]]
        b = model.coef_[0][1] / scaler.scale_[best_feature_ids[1]]
        c = model.intercept_[0] - model.coef_[0][0] * scaler.mean_[best_feature_ids[0]] / scaler.scale_[best_feature_ids[0]] \
                             - model.coef_[0][1] * scaler.mean_[best_feature_ids[1]] / scaler.scale_[best_feature_ids[1]]
        # a + b + c = 0 (<= 0 for constraint)
        # print(a * x_vals + b * y_vals + c)
        print(a*100, 'x', feature_names[best_feature_ids[0]], '+', b*100, 'x', feature_names[best_feature_ids[1]], '+', c, '= 0')  # 100 factor for pu conversion

        Path("SVMs").mkdir(exist_ok=True)
        plt.savefig('SVMs/{}_SVM_{}.pdf'.format(contingency_index, critical_contingency.get('id')))
        plt.close()

        # for i in range(len(colors)):
        #     color = colors[i]
        #     if color == 'green':
        #         c = 0
        #     elif color == 'red':
        #         c = 1
        #     elif color == 'yellow':
        #         c = 2
        #     else:
        #         c = 3
        #     print(samples[i, 0], samples[i, 1], c)
