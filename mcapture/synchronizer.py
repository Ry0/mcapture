import numpy as np
from typing import Dict, List, Optional, Tuple, Any, Union
from enum import Enum

import matplotlib.pyplot as plt


class SyncMethod(Enum):
    """時間同期方式の列挙型"""
    EXACT_TIME = 0         # 完全に一致するタイムスタンプのみ
    APPROXIMATE_TIME = 1   # 最も近いタイムスタンプ（時間許容範囲内）
    APPROXIMATE_EPSILON_TIME = 2  # 許容誤差と順序を考慮した近似タイムスタンプ
    LATEST_TIME = 3        # 各トピックの最新メッセージを使用


class Synchronizer:
    def __init__(self,
                 base_topic: str,
                 sync_method: SyncMethod = SyncMethod.APPROXIMATE_TIME,
                 time_tolerance: float = 0.1):
        """
        MCAPファイルから複数のトピックのデータを時間同期して取得するクラス

        Parameters:
        sync_method (SyncMethod): 時間同期方式
        time_tolerance (float): 許容する時間差（秒）
        base_topic (str, optional): 同期のベースとなるトピック。Noneの場合は最初のトピック
        """
        self.sync_method = sync_method
        self.time_tolerance = time_tolerance
        self.base_topic = base_topic

    def synchronize(self, data: Dict) -> List[Dict]:
        """
        選択した同期方式に基づいてデータを同期する

        Returns:
            List[Dict]: 同期されたデータフレームのリスト
        """

        if self.sync_method == SyncMethod.EXACT_TIME:
            return self._synchronize_exact_time(data)
        elif self.sync_method == SyncMethod.APPROXIMATE_TIME:
            return self._synchronize_approximate_time(data)
        elif self.sync_method == SyncMethod.APPROXIMATE_EPSILON_TIME:
            return self._synchronize_approximate_epsilon_time(data)
        elif self.sync_method == SyncMethod.LATEST_TIME:
            return self._synchronize_latest_time(data)
        else:
            raise ValueError(f"Unknown synchronization method: {self.sync_method}")

    def _to_nanoseconds(self, msg):
        if "header" not in msg:
            if "stamp" in msg:
                stamp = msg["stamp"]
            else:
                return 0
        else:
            stamp = msg["header"]["stamp"]
        # secs = stamp["secs"]
        # nsecs = stamp["nsecs"]
        secs = stamp["sec"]
        nsecs = stamp["nanosec"]

        return secs * 1_000_000_000 + nsecs

    def _from_nanoseconds(self, nanoseconds):
        # secs = nanoseconds // 1_000_000_000
        # nsecs = nanoseconds % 1_000_000_000

        # return {
        #     "secs": secs,
        #     "nsecs": nsecs
        # }
        secs = nanoseconds // 1_000_000_000
        nsecs = nanoseconds % 1_000_000_000

        return {
            "sec": secs,
            "nanosec": nsecs
        }

    def _synchronize_exact_time(self, data: Dict) -> List[Dict]:
        """
        完全に一致するタイムスタンプを持つメッセージのみを同期

        Returns:
            List[Dict]: 同期されたデータフレーム
        """
        # 各トピックのタイムスタンプを抽出
        timestamps_by_topic = {
            topic: set(self._to_nanoseconds(msg) for msg in msgs)
            for topic, msgs in data.items() if msgs
        }

        # すべてのトピックに共通するタイムスタンプを見つける
        common_timestamps = set.intersection(*timestamps_by_topic.values()) if timestamps_by_topic else set()

        # 同期データを生成
        synchronized_data = []
        for timestamp in sorted(common_timestamps):
            frame = {'stamp': self._from_nanoseconds(timestamp)}

            # 各トピックから同じタイムスタンプを持つメッセージを取得
            for topic, msgs in data.items():
                msg = next((m for m in msgs if self._to_nanoseconds(m) == timestamp), None)
                if msg:
                    frame[topic] = msg
            if len(frame) > 1:
                synchronized_data.append(frame)

        print(f"ExactTime sync: Found {len(synchronized_data)} synchronized frames")
        return synchronized_data

    def _synchronize_approximate_time(self, data: Dict) -> List[Dict]:
        """
        ベーストピックのタイムスタンプに最も近いメッセージを同期

        Returns:
            List[Dict]: 同期されたデータフレーム
        """
        # ベーストピックのメッセージが存在しない場合は空のリストを返す
        if not data[self.base_topic]:
            print(f"Base topic {self.base_topic} has no messages")
            return []

        synchronized_data = []

        # ベーストピックのメッセージをイテレート
        for base_msg in data[self.base_topic]:
            base_time = self._to_nanoseconds(base_msg)

            # この時間枠での同期データを格納する辞書
            frame = {
                'stamp': self._from_nanoseconds(base_time),
                self.base_topic: base_msg
            }

            # 他のトピックの近いメッセージを探す
            all_topics_found = True
            for topic in data:
                if topic == self.base_topic:
                    continue

                closest_msg = self._find_closest_message(
                    data[topic],
                    base_time,
                    # self.time_tolerance
                )

                if closest_msg:
                    frame[topic] = closest_msg
                else:
                    all_topics_found = False
                    break

            # すべての必須トピックが揃っていれば追加
            if all_topics_found:
                synchronized_data.append(frame)

        print(f"ApproximateTime sync: Found {len(synchronized_data)} synchronized frames")
        return synchronized_data

    def _synchronize_approximate_epsilon_time(self, data: Dict, queue_size: int = 100) -> List[Dict]:
        """
        ApproximateEpsilonTime同期方式

        Args:
            data: トピック名をキー、メッセージリストを値とする辞書
            queue_size: 各トピックのキューの最大サイズ

        Returns:
            List[Dict]: 同期されたデータフレーム
        """
        # 1. データの準備
        original_data = {topic: list(msgs) for topic, msgs in data.items() if msgs}

        # 2. すべてのトピックにメッセージがあるか確認
        if len(original_data) != len(data):
            print(f"一部のトピックにメッセージがありません。同期は実行されません。")
            return []

        # 3. 各トピックのメッセージキューとイテレータを初期化
        message_queues = {topic: [] for topic in original_data}
        data_iterators = {topic: iter(msgs) for topic, msgs in original_data.items()}

        # 4. 初期キューの充填
        for topic, iterator in data_iterators.items():
            self._fill_queue(topic, iterator, message_queues, queue_size)

        synchronized_data = []

        # 5. メインの同期ループ
        while True:
            # 5.1 空のキューがあるか確認し、あれば終了
            if any(len(queue) == 0 for queue in message_queues.values()):
                break

            # 5.2 各キューの先頭メッセージを取得
            heads = {topic: queue[0] for topic, queue in message_queues.items()}

            # 5.3 タイムスタンプを取得して最小と最大を見つける
            timestamps = {topic: self._to_nanoseconds(msg) for topic, msg in heads.items()}
            min_time = min(timestamps.values())
            max_time = max(timestamps.values())

            # 5.4 時間差がイプシロン以内かチェック
            time_diff = (max_time - min_time) / 1e9
            if time_diff <= self.time_tolerance:
                # 5.4.1 同期フレームを作成
                frame = {'stamp': self._from_nanoseconds(max_time)}
                for topic, msg in heads.items():
                    frame[topic] = msg

                synchronized_data.append(frame)

                # 5.4.2 使用したメッセージをすべてのキューから削除し、新しいメッセージを補充
                for topic in message_queues:
                    message_queues[topic].pop(0)
                    self._fill_queue(topic, data_iterators[topic], message_queues, queue_size)
            else:
                # 5.5 イプシロンを超える場合、最も古いメッセージを持つトピックだけを更新
                oldest_topics = [topic for topic, ts in timestamps.items() if ts == min_time]

                # 5.5.1 古いメッセージをキューから削除し、新しいメッセージを補充
                for topic in oldest_topics:
                    message_queues[topic].pop(0)
                    self._fill_queue(topic, data_iterators[topic], message_queues, queue_size)

        print(f"ApproximateEpsilonTime sync: Found {len(synchronized_data)} synchronized frames")
        return synchronized_data

    def _synchronize_latest_time(self, data: Dict) -> List[Dict]:
        """
        LatestTime同期方式の実装
        一定間隔でサンプリングし、その時点での各トピックの最新メッセージを使用

        Returns:
            List[Dict]: 同期されたデータフレーム
        """
        synchronized_data = []

        # すべてのトピックのタイムスタンプの最小値と最大値を取得
        all_timestamps = []
        for msgs in data.values():
            if msgs:
                all_timestamps.extend(
                    [ts for msg in msgs if (ts := self._to_nanoseconds(msg)) != 0]
                )

        if not all_timestamps:
            return []

        min_time = min(all_timestamps)
        max_time = max(all_timestamps)

        # サンプリング間隔を決定（例: 0.1秒ごと）
        sampling_interval = int(self.time_tolerance * 1e9)  # ナノ秒に変換

        # 各サンプリング時点での同期フレームを生成
        current_time = min_time
        while current_time <= max_time:
            frame = {'stamp': self._from_nanoseconds(current_time)}

            # 各トピックの現在時刻以前の最新メッセージを見つける
            all_required_found = True
            for topic in data:
                latest_msg = self._find_latest_message_before(data[topic], current_time)

                if latest_msg:
                    frame[topic] = latest_msg
                else:
                    all_required_found = False
                    break

            if all_required_found:
                synchronized_data.append(frame)

            # 次のサンプリング時点へ
            current_time += sampling_interval

        print(f"LatestTime sync: Found {len(synchronized_data)} synchronized frames")
        return synchronized_data

    def _find_closest_message(self, messages: List[Dict], target_time: int) -> Optional[Dict]:
        """
        指定した時間に最も近いメッセージを見つける

        Parameters:
            messages (List[Dict]): メッセージのリスト
            target_time (int): 対象の時間（ナノ秒）

        Returns:
            Optional[Dict]: 見つかったメッセージ、または時間許容範囲外ならNone
        """
        if not messages:
            return None

        # 二分探索で最も近いインデックスを見つける
        timestamps = [self._to_nanoseconds(msg) for msg in messages]
        index = np.searchsorted(timestamps, target_time)

        # 境界チェック
        if index == 0:
            closest_idx = 0
        elif index == len(messages):
            closest_idx = len(messages) - 1
        else:
            # 前後のどちらが近いか確認
            prev_diff = abs(target_time - timestamps[index - 1])
            curr_diff = abs(target_time - timestamps[index])
            closest_idx = index - 1 if prev_diff < curr_diff else index

        # 時間差を確認
        # time_diff_sec = abs(target_time - timestamps[closest_idx]) / 1e9

        # # 許容範囲内なら返す
        # if time_diff_sec <= max_diff_sec:
        #     return messages[closest_idx]
        # else:
        #     return None
        return messages[closest_idx]

    def _find_latest_message_before(self, messages: List[Dict], target_time: int) -> Optional[Dict]:
        """
        指定した時間以前の最新のメッセージを見つける

        Parameters:
            messages (List[Dict]): メッセージのリスト
            target_time (int): 対象の時間（ナノ秒）

        Returns:
            Optional[Dict]: 見つかったメッセージ、または条件を満たすメッセージがなければNone
        """
        if not messages:
            return None

        # 二分探索で挿入位置を見つける
        timestamps = [self._to_nanoseconds(msg) for msg in messages]
        index = np.searchsorted(timestamps, target_time, side='right')

        # target_time以前の最新メッセージのインデックス
        latest_idx = index - 1

        if latest_idx >= 0:
            return messages[latest_idx]
        else:
            return None

    def _fill_queue(self, topic, iterator, message_queues, queue_size):
        """
        指定されたトピックのキューを最大サイズまで補充する

        Args:
            topic: 対象トピック名
            iterator: メッセージを取得するイテレータ
            message_queues: 全トピックのメッセージキュー
            queue_size: キューの最大サイズ
        """
        current_size = len(message_queues[topic])
        if current_size >= queue_size:
            return

        # キューが最大サイズに達するまで、または利用可能なメッセージがなくなるまで補充
        try:
            for _ in range(queue_size - current_size):
                message = next(iterator)
                message_queues[topic].append(message)
        except StopIteration:
            # 新しいメッセージがなければ何もしない
            pass

    def plot(self, data: List[Dict], target_topics: List[str], save_path: Optional[str] = None):
        mod_indices = {mod: i for i, mod in enumerate(target_topics)}

        fig, ax = plt.subplots(figsize=(12, 3))
        # 水平線の描画（timestampも含む）
        ax.hlines(0, xmin=0, xmax=1, color='blue', linewidth=0.5)  # timestampのライン
        for mod in target_topics:
            ax.hlines(mod_indices[mod], xmin=0, xmax=1, color='black', linewidth=0.5)

        # 全データを処理
        all_times = []  # 時間範囲取得用
        for entry in data:
            # timestampのプロット（青い縦線）
            ts_time = self._to_nanoseconds(entry) / 1e9
            if ts_time != 0:
                all_times.append(ts_time)
            ax.axvline(ts_time, color='blue', linestyle='-', linewidth=1)

            connected_points = []
            for mod in target_topics:
                if mod in entry:
                    t = self._to_nanoseconds(entry[mod]) / 1e9
                    if t != 0:
                        all_times.append(t)
                    ax.plot(t, mod_indices[mod], 'o', color='red', markersize=5)
                    connected_points.append((t, mod_indices[mod]))
            # 線で接続（同じ辞書内のモダリティ間）
            if len(connected_points) >= 2:
                xs, ys = zip(*connected_points)
                ax.plot(xs, ys, color='black', linewidth=0.5, linestyle='dotted')

        # 軸とグリッド設定
        ax.set_yticks([0] + list(mod_indices.values()))
        ax.set_yticklabels(['timestamp'] + target_topics)
        ax.set_xlabel("Time (s)")
        ax.set_title("Time synchronization of multimodal time series data")

        # 等間隔グリッド
        if all_times:
            min_t, max_t = min(all_times), max(all_times)
            margin = 0.1
            min_t -= margin
            max_t += margin
            ax.set_xlim(min_t, max_t)

            # grid_interval = 0.1
            # xticks = np.arange(
            #     np.floor(min_t / grid_interval) * grid_interval,
            #     np.ceil(max_t / grid_interval) * grid_interval + grid_interval,
            #     grid_interval)
            # ax.set_xticks(xticks)
            # ax.grid(True, axis='x', linestyle='--', alpha=0.5)

        plt.tight_layout()

        if save_path is not None:
            plt.savefig(save_path)
        else:
            plt.show()

if __name__ == "__main__":
    pass
