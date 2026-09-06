"""採用した画像と相対的な使用頻度を、学習器の既存サブセット設定へ渡す。"""
import json


def dataset_config(job: dict, remote_directory: str) -> str:
    # 優先画像を通常の2倍使う。総ステップ数は維持し、特徴の完全分離は行わない。
    weights = {"primary": 2, "normal": 1}
    if job.get("training_selection"):
        counts = {priority: sum(m["training_policy"]["priority"] == priority for m in job["materials"]) for priority in weights}
        unit = max(1, 200 // sum(counts[p] * weights[p] for p in weights))
        subsets = [(f"{remote_directory}/{p}", unit * weights[p]) for p in weights if counts[p]]
    else:
        # 過去に凍結した教材は、その当時の全画像・等頻度を保つ。
        subsets = [(remote_directory, max(1, 200 // job["images"]))]
    return '[[datasets]]\nresolution = 1024\nbatch_size = 1\nenable_bucket = true\n' + ''.join(
        f'[[datasets.subsets]]\nimage_dir = {json.dumps(path)}\ncaption_extension = ".txt"\nnum_repeats = {repeats}\n'
        for path, repeats in subsets)
