import numpy as np
from typing import Dict, List, Optional, Tuple, Any, Union
from enum import Enum
import datetime
import matplotlib.pyplot as plt


class Synchronizer:
    def __init__(self):
        """
        MCAPファイルから複数のトピックのデータを時間同期して取得するクラス
        """

    def synchronize_exact_time(self, data: Dict) -> List[Dict]:
        """
        ROS2のExactTime同期方式を再現した実装

        Args:
            data: トピック名をキー、メッセージリストを値とする辞書

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

    def synchronize_approximate_time(self, data: Dict, queue_size: int = 100, min_queue_size: int = 10, max_interval_duration: float = 0.1) -> List[Dict]:
        """
        ROS2のApproximateTime同期方式を再現した実装

        Args:
            data: トピック名をキー、メッセージリストを値とする辞書
            queue_size: 各トピックのキューの最大サイズ
            min_queue_size: 組み合わせ計算をするときに確保するサイズ数
            max_interval_duration: 同期が見つからない場合に古いメッセージを破棄するための最大時間間隔（秒）

        Returns:
            List[Dict]: 同期されたデータフレーム
        """
        # 1. データの準備
        original_data = {topic: list(msgs) for topic, msgs in data.items() if msgs}

        # 2. すべてのトピックにメッセージがあるか確認
        if len(original_data) != len(data):
            print("一部のトピックにメッセージがありません。同期は実行されません。")
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

            # 5.2 最適な同期組み合わせを見つける
            best_combination, best_score = self._find_best_combination(message_queues, min_queue_size)

            # 5.3 同期が見つかった場合
            if best_combination:
                # 5.3.1 同期フレームを作成
                pivot_time = self._calculate_pivot_time(best_combination, message_queues)
                frame = {'stamp': self._from_nanoseconds(pivot_time)}

                for topic, idx in best_combination.items():
                    frame[topic] = message_queues[topic][idx]

                synchronized_data.append(frame)

                # 5.3.2 使用したメッセージとそれより古いメッセージを削除し、新しいメッセージを補充
                for topic, idx in best_combination.items():
                    # インデックスまでのメッセージをすべて削除（使用したメッセージを含む）
                    for _ in range(idx + 1):
                        if message_queues[topic]:
                            message_queues[topic].pop(0)

                    # キューを補充
                    self._fill_queue(topic, data_iterators[topic], message_queues, queue_size)
            else:
                # 5.4 同期が見つからない場合、各キューの先頭のタイムスタンプを確認
                timestamps = {topic: self._to_nanoseconds(queue[0]) for topic, queue in message_queues.items() if queue}

                if not timestamps:
                    break

                min_time = min(timestamps.values())
                max_time = max(timestamps.values())

                # 5.4.1 最大時間間隔を超える場合、最も古いメッセージを持つトピックのメッセージを削除
                if (max_time - min_time) / 1e9 > max_interval_duration:
                    oldest_topics = [topic for topic, ts in timestamps.items() if ts == min_time]

                    for topic in oldest_topics:
                        if message_queues[topic]:
                            message_queues[topic].pop(0)
                            self._fill_queue(topic, data_iterators[topic], message_queues, queue_size)
                else:
                    # 5.4.2 時間間隔が小さい場合は、より多くのメッセージを読み込んで再試行
                    # この場合、各キューに最低1つは新しいメッセージを追加
                    for topic, iterator in data_iterators.items():
                        try:
                            message = next(iterator)
                            message_queues[topic].append(message)
                            # キューサイズを超えた場合、古いメッセージを削除
                            if len(message_queues[topic]) > queue_size:
                                message_queues[topic].pop(0)
                        except StopIteration:
                            pass

                    # すべてのイテレータが終了した場合は終了
                    if all(len(list(iterator)) == 0 for iterator in data_iterators.values()):
                        break

        print(f"ApproximateTime sync: Found {len(synchronized_data)} synchronized frames")
        return synchronized_data

    def synchronize_approximate_epsilon_time(self, data: Dict, queue_size: int = 100, epsilon_sec=0.1) -> List[Dict]:
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
            print("一部のトピックにメッセージがありません。同期は実行されません。")
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
            if time_diff <= epsilon_sec:
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

    def synchronize_latest_time(self, data: Dict, sampling_interval_sec: float = 0.1) -> List[Dict]:
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
        sampling_interval = int(sampling_interval_sec * 1e9)  # ナノ秒に変換

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

    def _find_best_combination(self, message_queues, min_queue_size=10):
        """
        すべてのメッセージキューから最適な同期組み合わせを見つける

        Args:
            message_queues: 全トピックのメッセージキュー

        Returns:
            best_combination: トピック名とインデックスのマッピング
            best_score: 最適な組み合わせのスコア（低いほど良い）
        """
        if any(len(queue) == 0 for queue in message_queues.values()):
            return None, float('inf')

        # すべての可能な組み合わせを生成
        topic_indices = {topic: list(range(min(min_queue_size, len(queue)))) for topic, queue in message_queues.items()}
        combinations = self._generate_combinations(topic_indices)

        best_combination = None
        best_score = float('inf')

        # 各組み合わせを評価
        for combination in combinations:
            # 組み合わせからメッセージを選択
            selected_msgs = {topic: message_queues[topic][idx] for topic, idx in combination.items()}

            # ピボットタイムスタンプを計算
            pivot_time = self._calculate_pivot_time(combination, message_queues)

            # スコアを計算（タイムスタンプの差の二乗和）
            score = sum((self._to_nanoseconds(msg) - pivot_time) ** 2 for msg in selected_msgs.values())

            # より良いスコアが見つかれば更新
            if score < best_score:
                best_score = score
                best_combination = combination

        return best_combination, best_score

    def _generate_combinations(self, topic_indices):
        """
        すべてのトピックのインデックスからすべての可能な組み合わせを生成

        Args:
            topic_indices: トピック名とそのインデックスリストのマッピング

        Returns:
            combinations: 可能なすべての組み合わせのリスト
        """
        topics = list(topic_indices.keys())

        if not topics:
            return []

        # 最初のトピックから始める
        combinations = [{topics[0]: idx} for idx in topic_indices[topics[0]]]

        # 残りのトピックを順番に追加
        for i in range(1, len(topics)):
            topic = topics[i]
            new_combinations = []

            for combination in combinations:
                for idx in topic_indices[topic]:
                    new_combination = combination.copy()
                    new_combination[topic] = idx
                    new_combinations.append(new_combination)

            combinations = new_combinations

        return combinations

    def _calculate_pivot_time(self, combination, message_queues):
        """
        与えられた組み合わせからピボットタイムスタンプを計算

        Args:
            combination: トピック名とインデックスのマッピング
            message_queues: 全トピックのメッセージキュー

        Returns:
            pivot_time: 平均タイムスタンプ（ナノ秒）
        """
        # if message_queues:
        #     # インデックスからメッセージを取得する場合
        # else:
        #     # すでにメッセージが渡されている場合
        #     timestamps = [self._to_nanoseconds(msg) for topic, msg in combination.items()]
        timestamps = [self._to_nanoseconds(message_queues[topic][idx]) for topic, idx in combination.items()]

        # 平均タイムスタンプを返す
        return sum(timestamps) // len(timestamps)

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

    def plot(self, data: List[Dict], target_topics: List[str], save_path: Optional[str] = None):
        mod_indices = {mod: i for i, mod in enumerate(target_topics)}
        fig, ax = plt.subplots(figsize=(12, 3))

        # 全データから時間情報を収集
        all_times = []  # 時間範囲取得用
        for entry in data:
            # timestampのナノ秒時間
            ts_time = self._to_nanoseconds(entry) / 1e9
            if ts_time != 0:
                all_times.append(ts_time)

            # 各モダリティのナノ秒時間
            for mod in target_topics:
                if mod in entry:
                    t = self._to_nanoseconds(entry[mod]) / 1e9
                    if t != 0:
                        all_times.append(t)

        # 最小時間を基準とする（スタート時間）
        if all_times:
            base_time = min(all_times)
            start_datetime = datetime.datetime.fromtimestamp(base_time)
            start_time_str = start_datetime.strftime('%Y-%m-%d %H:%M:%S')

            # プロットの描画（基準時間からの相対時間に変換）
            for entry in data:
                # timestampのプロット（青い縦線）
                ts_time = self._to_nanoseconds(entry) / 1e9
                if ts_time != 0:
                    relative_ts_time = ts_time - base_time
                    ax.axvline(relative_ts_time, color='blue', linestyle='-', linewidth=1)

                connected_points = []
                for mod in target_topics:
                    if mod in entry:
                        t = self._to_nanoseconds(entry[mod]) / 1e9
                        if t != 0:
                            relative_t = t - base_time
                            ax.plot(relative_t, mod_indices[mod], 'o', color='red', markersize=5)
                            connected_points.append((relative_t, mod_indices[mod]))

                # 線で接続（同じ辞書内のモダリティ間）
                if len(connected_points) >= 2:
                    xs, ys = zip(*connected_points)
                    ax.plot(xs, ys, color='black', linewidth=0.5, linestyle='dotted')

            # 軸とグリッド設定
            ax.set_yticks([0] + list(mod_indices.values()))
            ax.set_yticklabels(['timestamp'] + target_topics)
            ax.set_xlabel("Time from start (s)")
            ax.set_title(f"Time synchronization of multimodal time series data\nStart time: {start_time_str}")

            # 表示範囲設定
            min_t, max_t = 0, max(all_times) - base_time
            margin = 0.1 * (max_t - min_t)
            ax.set_xlim(-margin, max_t + margin)

            # 水平線の描画
            ax.hlines(0, xmin=0, xmax=max_t, color='gray', linewidth=0.2)  # timestampのライン
            for mod in target_topics:
                ax.hlines(mod_indices[mod], xmin=0, xmax=max_t, color='gray', linewidth=0.2)

            # x_major_ticks = np.arange(0, max_t, 1)
            # x_minor_ticks = np.arange(0, max_t, 0.1)

            # # major_ticksは少し太めの黒,minor_ticksは灰色で透過度0.5
            # ax.tick_params(length=6, width=2, grid_color='black', grid_alpha=1.0)
            # ax.tick_params(which='minor', grid_color='gray', grid_alpha=0.5)
            # ax.set_xticks(x_major_ticks)
            # ax.set_xticks(x_minor_ticks, minor=True)
            # ax.grid(which='both')

            plt.tight_layout()
            if save_path is not None:
                plt.savefig(save_path)
            else:
                plt.show()
        else:
            print("No valid time data found.")


if __name__ == "__main__":
    pass
