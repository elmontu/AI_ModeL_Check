"""Pinned SACRO-ML probability-only fixture runtime; no model deserialization.

Source/RECORD checks detect installed-source drift in this trusted local process.
They do not authenticate a host, sandbox imports, or approve model/data release.
Install the pinned upstream wheel with --no-compile and invoke Python with -B.
"""
from __future__ import annotations

import base64
import csv
import hashlib
import importlib
import importlib.metadata
import importlib.util
import io
import math
import os
from pathlib import Path
import platform
import stat
import sys

from ..production_adapters import native
from ..production_adapters.contracts import canonical_bytes

SACRO_VERSION = "2.0.1"
WHEEL_SHA256 = "8b0d5d9b32cff57d283a82722cbd244560d04cb6184ae7c493c6c94496957741"
METADATA_SHA256 = "5e73a99e94b75ae1b19ff8077cdf42596b9fcf26f99de43f3187fda4040b41b3"
SEEDS = (20261001, 20261002, 20261003)
NUMERICAL_VERSIONS = {"python": "3.12.14", "numpy": "2.5.3", "scipy": "1.18.1",
                      "scikit-learn": "1.6.1", "joblib": "1.6.0", "threadpoolctl": "3.7.0"}
# Derived from the official PyPI wheel whose full digest is WHEEL_SHA256.
SOURCE_PINS = {'sacroml/__init__.py': {'sha256': 'e1cb2953a1253bdb9eeefa6b440f9ef6c3b8741afbce64370d4c5484ec1583a2', 'size_bytes': 82}, 'sacroml/main.py': {'sha256': '14039fc293ae60e03c06cd24fd184a7f0a4284e1133f7de6c0260ce331df630e', 'size_bytes': 1375}, 'sacroml/metrics.py': {'sha256': 'fc3123d2bc23b2baadaf6460ca9df720f32de1969c6fb8bca52d07c95408ebb3', 'size_bytes': 10950}, 'sacroml/version.py': {'sha256': 'bc0d8015bc300d973e7d161fb6c443efafa03ae69d828bb7b1e9b4078d47e0ec', 'size_bytes': 54}, 'sacroml/attacks/__init__.py': {'sha256': 'ad3ae965480575ed96bb0e8911c6456b6b2ab98ba768be87c9ac1016235e1887', 'size_bytes': 76}, 'sacroml/attacks/_scorers.py': {'sha256': 'd0e0fc0a6d1ddb94449e20958ff59fd8d625f221387713c35af618fd37347375', 'size_bytes': 4106}, 'sacroml/attacks/attack.py': {'sha256': '18743166186f994269b3c3ffb1d3e3c8575ee9cdcf46bc40ffec0231cf1daa27', 'size_bytes': 5360}, 'sacroml/attacks/attack_report_formatter.py': {'sha256': 'cbde843d4f860750bc25fa8714917580bccda2670d6d64c0380be57cb2b81568', 'size_bytes': 24411}, 'sacroml/attacks/attribute_attack.py': {'sha256': 'c846c42798ef0946d9c6c72ee2d115e1e7fcb12d388200a1d4ddd3b4aeeb5dbc', 'size_bytes': 23968}, 'sacroml/attacks/constants.py': {'sha256': '980b83db3e610dcbf60f0b8f426380a1f14a884f5e4bf9acfcb8641fca04adc1', 'size_bytes': 1302}, 'sacroml/attacks/data.py': {'sha256': '8eef0524aa644774e13aff75636e1c4c97d3eb182a31b9716aa1f22b2a936d38', 'size_bytes': 2918}, 'sacroml/attacks/factory.py': {'sha256': '676865e5aa721ad0e81451e66e48bae09ff2b0f2f9ce9e4e29620f55f8400337', 'size_bytes': 2331}, 'sacroml/attacks/instance_based_attack.py': {'sha256': 'b3044cd05df6a0e97f9049e6cea636ecb7295e0248cd3f39bd9cdc57dcbe8a82', 'size_bytes': 19677}, 'sacroml/attacks/likelihood_attack.py': {'sha256': 'c6342cc47f0ee5a4d196801c42533c52612d64c4adcaaaa06b28d728afc09b31', 'size_bytes': 15907}, 'sacroml/attacks/meta_attack.py': {'sha256': 'f6b0b8794fcbeba37d0eef44cc604952d8a6c73dac05f3c92857fc943f52860d', 'size_bytes': 32935}, 'sacroml/attacks/model.py': {'sha256': '52597f3b360c13e9ffd6e26ad95d95412d8960eb45b971a7c7a1b228a4e87e63', 'size_bytes': 10339}, 'sacroml/attacks/model_pytorch.py': {'sha256': 'e936fb5f80cf329758f04629acf0eaa1b43cb47b9c5e4ab7a52afbdf9857f2b9', 'size_bytes': 15530}, 'sacroml/attacks/model_sklearn.py': {'sha256': '2fda0ead41f8524c8aba809c074817721d30e1c00d187bf5e7fc5f49d5e301b1', 'size_bytes': 8504}, 'sacroml/attacks/qmia_attack.py': {'sha256': 'b5ddbbd4b72f0e19fc392b779dea06d9d4b062d68cb23eb70ec65551f6968607', 'size_bytes': 12284}, 'sacroml/attacks/report.py': {'sha256': '24ade5aa06b2beea89d0782587e5153a004449cbb7ff786575bf527ef6cf54f4', 'size_bytes': 28023}, 'sacroml/attacks/structural_attack.py': {'sha256': '183b363d808064ff43d3877bb70e42e712f8b0cadc11ba2a0c398dcd3d9093e4', 'size_bytes': 26926}, 'sacroml/attacks/target.py': {'sha256': '7b3ddd44a5cdf537947a58c73e0bd283286cb6265c326f028fe67411872e11d5', 'size_bytes': 19384}, 'sacroml/attacks/utils.py': {'sha256': '13c1f7e4d84863e7dbf5889c321a5c4adedc2d2a2c04576752fe883d314f65e1', 'size_bytes': 10421}, 'sacroml/attacks/worst_case_attack.py': {'sha256': '9d55ffc651b565efc5ec5f4c06b2e47c463763a2e1eaf7ced00169b000499bcc', 'size_bytes': 29549}, 'sacroml/config/__init__.py': {'sha256': '84bedee1b6b62cf1e98c19044f7652c68c7871d5139bf9b51fd43e067bda838e', 'size_bytes': 48}, 'sacroml/config/attack.py': {'sha256': '437e885e1b80fbf0fc9c59bb74c621007e3edf400a00dba28d51db0d37ffe8e9', 'size_bytes': 2986}, 'sacroml/config/target.py': {'sha256': 'a6f1cee468924a632a8e0c8e45e25d51f9bbb7654e453b5170dc75654e8798ad', 'size_bytes': 12569}, 'sacroml/config/utils.py': {'sha256': '796456fa2eace681870ce22691fbf4314cc169f22347241abf0a80023975999b', 'size_bytes': 2014}, 'sacroml/safemodel/__init__.py': {'sha256': '7d6e386c90821c4c3db1fce5540aee8db0d4bedd21bc2d92db5fadf8243b5536', 'size_bytes': 80}, 'sacroml/safemodel/reporting.py': {'sha256': '2a1cb601eafca2632cf77b36c4d4e6cbac00b8173d97e29fdc8edb8d40d725e6', 'size_bytes': 10955}, 'sacroml/safemodel/rules.json': {'sha256': '1c2d6c0a5ad0d3ea46cf32ee7cdb11537c0d1e007c939d047a8aecb976007050', 'size_bytes': 4986}, 'sacroml/safemodel/safemodel.py': {'sha256': '42bd9db1c6973b3f501b61612a9f3efca6835296469c273055adf0c79e7bb627', 'size_bytes': 23094}, 'sacroml/safemodel/classifiers/__init__.py': {'sha256': '6d4151df5a4980a05fa2ebb3cdefc348e43f4bd81b54eb16812f15eceba2a9b4', 'size_bytes': 330}, 'sacroml/safemodel/classifiers/dp_svc.py': {'sha256': '39705b815990038b81a3375f08e91ff665c6dde8c5928ba808521627dec31fed', 'size_bytes': 7734}, 'sacroml/safemodel/classifiers/new_model_template.py': {'sha256': '5ab04f5105aeeb41acdfb01eaf9b1f0d0c6ebcc6d5430758d31ca3c742bb04fb', 'size_bytes': 7697}, 'sacroml/safemodel/classifiers/safedecisiontreeclassifier.py': {'sha256': 'e723fc9d2a54648eaa9ebf8735dfb601b045a7ce9d83f6d708138bd5cd15fc4d', 'size_bytes': 6364}, 'sacroml/safemodel/classifiers/saferandomforestclassifier.py': {'sha256': '1cd655eb89dbf53315a585a98845ecdbf0873f652e0984b8e3105facd4bb968c', 'size_bytes': 5882}, 'sacroml/safemodel/classifiers/safesvc.py': {'sha256': 'defab34e207ffe71cd4956a03c110c7ad10b44638b1c14ea3f8d9cbf02233e32', 'size_bytes': 1945}}
ATTACK_PARAMETERS = {"n_estimators": 32, "max_depth": 5, "min_samples_leaf": 10,
                     "min_samples_split": 20, "n_jobs": 1, "random_state": SEEDS[0]}


class SacroRuntimeError(ValueError):
    """The bounded imported fixture runtime could not be verified or executed."""


def _fail():
    raise SacroRuntimeError("SACRO fixture runtime rejected")


def _digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _file(path, maximum):
    return native._read(Path(path), maximum)


def _numerical_versions():
    return {"python": platform.python_version(), **{name: importlib.metadata.version(name)
            for name in NUMERICAL_VERSIONS if name != "python"}}


def _check_modules(base):
    for name, module in tuple(sys.modules.items()):
        if name != "sacroml" and not name.startswith("sacroml."):
            continue
        if module is None:
            _fail()
        relative = name.replace(".", "/")
        candidates = [relative + ".py", relative + "/__init__.py"]
        expected = [base / item for item in candidates if item in SOURCE_PINS]
        actual = getattr(module, "__file__", None)
        spec = getattr(module, "__spec__", None)
        if (len(expected) != 1 or not actual or Path(actual).absolute() != expected[0]
                or spec is None or Path(str(spec.origin)).absolute() != expected[0]):
            _fail()
        if expected[0].name == "__init__.py":
            locations = list(getattr(module, "__path__", []))
            if locations != [str(expected[0].parent)]:
                _fail()


def _checked_distribution(distribution):
    if distribution.version != SACRO_VERSION:
        _fail()
    base = Path(distribution.locate_file("")).absolute()
    package = base / "sacroml"
    native._real_directory(package)
    metadata = base / ("sacroml-" + SACRO_VERSION + ".dist-info")
    if hashlib.sha256(_file(metadata / "METADATA", 256 * 1024)).hexdigest() != METADATA_SHA256:
        _fail()
    rows = list(csv.reader(io.StringIO(_file(metadata / "RECORD", 1024 * 1024).decode("utf-8"))))
    if not 1 <= len(rows) <= 1024 or any(len(row) != 3 for row in rows):
        _fail()
    record = {}
    for name, value, size in rows:
        if name in record:
            _fail()
        record[name] = (value, size)
    actual = set()
    for folder, dirs, files in os.walk(package, followlinks=False):
        for dirname in dirs:
            info = (Path(folder) / dirname).lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                _fail()
        for filename in files:
            relative = (Path(folder) / filename).relative_to(base).as_posix()
            actual.add(relative)
            if relative not in SOURCE_PINS or len(actual) > 128:
                _fail()
    if actual != set(SOURCE_PINS):
        _fail()
    for name, pin in SOURCE_PINS.items():
        raw = _file(base / name, pin["size_bytes"])
        expected_record = "sha256=" + base64.urlsafe_b64encode(bytes.fromhex(pin["sha256"])).decode("ascii").rstrip("=")
        if (len(raw) != pin["size_bytes"] or hashlib.sha256(raw).hexdigest() != pin["sha256"]
                or record.get(name) != (expected_record, str(pin["size_bytes"]))):
            _fail()
    spec = importlib.util.find_spec("sacroml")
    if (spec is None or not spec.origin or Path(spec.origin).absolute() != package / "__init__.py"
            or list(spec.submodule_search_locations or []) != [str(package)]):
        _fail()
    _check_modules(base)
    return base


def runtime_binding():
    """Check the pinned source before optional SACRO imports, without a cache."""
    try:
        _checked_distribution(importlib.metadata.distribution("sacroml"))
        versions = _numerical_versions()
        if versions != NUMERICAL_VERSIONS:
            _fail()
        return {"schema": "mra-sacro-runtime-binding/v1", "sacroml_version": SACRO_VERSION,
                "wheel_sha256": WHEEL_SHA256, "metadata_sha256": METADATA_SHA256,
                "package_sha256": _digest(SOURCE_PINS), "source_files": len(SOURCE_PINS),
                "numerical_versions": dict(versions), "fixture_only": True,
                "production_authorized": False, "model_delivery": False}
    except Exception:
        raise SacroRuntimeError("SACRO fixture runtime rejected") from None


def _load_attack():
    module = importlib.import_module("sacroml.attacks.worst_case_attack")
    return module.WorstCaseAttack


def _probabilities(value):
    import numpy as np
    if isinstance(value, (list, tuple)):
        if any(not isinstance(row, (list, tuple)) or any(type(item) not in (int, float) for item in row) for row in value):
            _fail()
    array = np.asarray(value)
    if array.dtype.kind not in {"f", "i", "u"} or array.ndim != 2:
        _fail()
    if not 20 <= array.shape[0] <= 4096 or not 2 <= array.shape[1] <= 32:
        _fail()
    array = np.array(array, dtype=np.float64, copy=True, order="C")
    if (not np.isfinite(array).all() or np.any(array < 0) or np.any(array > 1)
            or not np.allclose(array.sum(axis=1), 1., rtol=0., atol=1e-12)):
        _fail()
    return array


def _number(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
        _fail()
    return float(value)


def run_attack(member_probabilities, nonmember_probabilities, *, output_dir):
    """Run one fixed imported attack recipe on owned numeric probabilities.

    Returned indices refer to members followed by nonmembers. SACRO's public
    no-tuning splitter is independently reconstructed and labels checked. Only
    required finite outputs are retained; upstream PDF/NPZ reporting is disabled.
    ``output_dir`` must be fresh because SACRO creates shadow-model directories
    even with report writing disabled. This adapter never uses those model APIs.
    """
    try:
        import numpy as np
        from sklearn.model_selection import train_test_split
        members, nonmembers = _probabilities(member_probabilities), _probabilities(nonmember_probabilities)
        if members.shape[1] != nonmembers.shape[1] or len(members) + len(nonmembers) > 4096:
            _fail()
        before = runtime_binding()
        output = native._new_output(output_dir)
        factory = _load_attack()
        if canonical_bytes(runtime_binding()) != canonical_bytes(before):
            _fail()
        attack = factory(output_dir=str(output), write_report=False, n_reps=3,
                         reproduce_split=list(SEEDS), n_dummy_reps=0, test_prop=.5,
                         include_model_correct_feature=False, sort_probs=True,
                         attack_model="sklearn.ensemble.RandomForestClassifier",
                         attack_model_params=dict(ATTACK_PARAMETERS),
                         attack_model_param_grid=None, report_individual=True)
        result = attack.run_attack_reps(members, nonmembers)
        if type(result) is not dict or set(result) != {"mia_metrics"}:
            _fail()
        metrics = result["mia_metrics"]
        if type(metrics) is not list or len(metrics) != len(SEEDS):
            _fail()
        labels = np.array([1] * len(members) + [0] * len(nonmembers), dtype=np.int64)
        indices = np.arange(len(labels))
        owned = []
        for seed, metric in zip(SEEDS, metrics, strict=True):
            train, test = train_test_split(indices, test_size=.5, stratify=labels,
                                          random_state=seed, shuffle=True)
            if type(metric) is not dict or "individual" not in metric or "AUC" not in metric:
                _fail()
            individual = metric["individual"]
            if type(individual) is not dict or set(individual) != {"member", "member_prob"}:
                _fail()
            actual_labels, probabilities = individual["member"], individual["member_prob"]
            if (type(actual_labels) is not list or type(probabilities) is not list
                    or len(actual_labels) != len(test) or len(probabilities) != len(test)):
                _fail()
            expected_labels = labels[test].tolist()
            if [_number(value) for value in actual_labels] != expected_labels:
                _fail()
            owned.append({"seed": seed, "train_indices": train.tolist(), "test_indices": test.tolist(),
                          "membership_labels": expected_labels,
                          "member_probabilities": [_number(value) for value in probabilities],
                          "upstream_auc": _number(float(metric["AUC"])) if type(metric["AUC"]) is np.float64 else _number(metric["AUC"])})
        if canonical_bytes(runtime_binding()) != canonical_bytes(before):
            _fail()
        return owned
    except Exception:
        raise SacroRuntimeError("SACRO fixture runtime rejected") from None
