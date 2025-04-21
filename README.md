# Mcapture
このモジュールは、ROS2のrosbag機能を使って保存したMCAPファイルをロードしてPython標準の辞書データに変換する機能、
変換したマルチモーダルなデータを時間同期する機能（ROS2のmessage filters機能を再現）を提供しています。

## 機能
MCAPをロードする機能。

```python
from mcapture.mcap_loader import McapLoader

base_path = os.path.dirname(os.path.abspath(__file__))
mcap_file_name = "rosbag2_2025_04_20-16_32_05/rosbag2_2025_04_20-16_32_05_0.mcap"
mcap_file_path = os.path.join(base_path, "data", mcap_file_name)

target_topics = [
    "/joint_states",
    "/camera/camera/color/image_rect_raw",
    "/image_raw"
]

loader = McapLoader()
load_result = loader.load_mcap(mcap_file_path, target_topics)

print(f"Topic list: {load_result.keys()}")
for key in load_result:
    print(f"Topic name: {key}, Data length: {len(load_result[key])}")
```

マルチモーダルなデータの時間同期を行う際に、同期方式に対応。

> [!IMPORTANT]
> ROS2のmessage filters機能を完全に再現したものではありません。
> 独自の解釈も含まれます。

* `ExactTime`: 完全に同じタイムスタンプを持つメッセージのみを同期
* `ApproximateTime`: 時間的に近いメッセージの最適な組み合わせを見つける
* `ApproximateEpsilonTime`: 指定した時間間隔以内にあるメッセージを同期
* `LatestTime`: 特定の時間間隔でサンプリングし、最新のメッセージを使用

```python
from synchronizer import Synchronizer

# 同期器のインスタンス化
sync = Synchronizer()

# データの準備（McapLoaderdでロードしたものを使用する）
data = {
    "/joint_states": [メッセージリスト1],
    "/camera/camera/color/image_rect_raw": [メッセージリスト2],
    "/image_raw": [メッセージリスト3]
}

# 同期方式の選択
# 1. ExactTime同期
exact_sync_data = sync.synchronize_exact_time(data)

# 2. ApproximateTime同期
approx_sync_data = sync.synchronize_approximate_time(data, queue_size=100)

# 3. ApproximateEpsilonTime同期
epsilon_sync_data = sync.synchronize_approximate_epsilon_time(data, epsilon_sec=0.1)

# 4. LatestTime同期
latest_sync_data = sync.synchronize_latest_time(data, sampling_interval_sec=0.1)
```


同期されたデータを時系列で可視化できる機能。

```python
# 同期結果の可視化
sync.plot(exact_sync_data, ['topic1', 'topic2', 'topic3'])
```

## 同期アルゴリズムの概要
### ExactTime
完全に同じタイムスタンプを持つメッセージのみを同期します。全てのトピックが共通のタイムスタンプを持つ場合にのみデータフレームが生成されます。

### ApproximateTime
時間的に近いメッセージの最適な組み合わせを見つけます。各トピックのメッセージをキューに保存し、タイムスタンプの差が最小になる組み合わせを探索します。

![image](.image/Figure_1.png)

### ApproximateEpsilonTime
指定した時間間隔（イプシロン）以内にあるメッセージを同期します。各トピックの先頭メッセージ間の時間差がイプシロン以内であれば同期対象となります。

![image](.image/Figure_2.png)

### LatestTime
一定の時間間隔でサンプリングし、各サンプリング時点での各トピックの最新メッセージを使用します。

![image](.image/Figure_3.png)

## ライセンス
MIT Lisence