from mcap.reader import make_reader
import mcap_ros2
from mcap_ros2.decoder import Decoder as Ros2Decoder
from mcap_ros1.decoder import Decoder as Ros1Decoder
import numpy as np
from typing import Dict, List, Optional, Tuple, Any, Union
from enum import Enum
from tqdm import tqdm

import matplotlib.pyplot as plt


class SyncMethod(Enum):
    """時間同期方式の列挙型"""
    EXACT_TIME = 0         # 完全に一致するタイムスタンプのみ
    APPROXIMATE_TIME = 1   # 最も近いタイムスタンプ（時間許容範囲内）
    APPROXIMATE_EPSILON_TIME = 2  # 許容誤差と順序を考慮した近似タイムスタンプ
    LATEST_TIME = 3        # 各トピックの最新メッセージを使用


class McapLoader:
    def __init__(self):
        """
        MCAPファイルから複数のトピックのデータを時間同期して取得するクラス

        Parameters:
        mcap_file (str): MCAPファイルのパス
        topics_config (Dict[str, Dict]): トピック設定。キーはトピック名、値は設定辞書
            例: {
                "/joint_states": {"alias": "joints", "required": True},
                "/camera/image": {"alias": "camera1", "required": False}
            }
        sync_method (SyncMethod): 時間同期方式
        time_tolerance (float): 許容する時間差（秒）
        epsilon (float): ApproximateEpsilonTimeで使用する許容誤差（秒）
        base_topic (str, optional): 同期のベースとなるトピック。Noneの場合は最初のトピック
        """

    def load_mcap(self, mcap_file: str, target_topics: List[str]):
        load_result = {}

        """MCAPファイルからメッセージを読み込む"""
        ros2_decoder = mcap_ros2.decoder.DecoderFactory()
        with open(mcap_file, "rb") as f:
            reader = make_reader(f, decoder_factories=[ros2_decoder])
            # reader = mcap.reader.make_reader(open(mcap_file, "rb"))
            topics_found = set()

            for schema, channel, message in tqdm(reader.iter_messages(), desc="Reading messages", unit="msg"):
                topic = channel.topic

                # 指定したトピックのみを処理
                if topic in target_topics:
                    topics_found.add(topic)
                    # メッセージタイプを取得してデシリアライズ
                    decoder = Ros2Decoder()
                    msg = decoder.decode(schema, message)

                    if topic not in load_result:
                        load_result[topic] = []
                    # タイムスタンプとメッセージを保存
                    load_result[topic].append(self._ros_message_to_dict(msg))

        # 指定したトピックがMCAPに存在するか確認
        missing_topics = set(target_topics) - topics_found
        if missing_topics:
            raise ValueError(f"Required topics not found: {missing_topics}")

        # タイムスタンプでソート
        for topic in target_topics:
            load_result[topic].sort(key=lambda x: self._to_nanoseconds(x))
            print(f"Loaded {len(load_result[topic])} messages from {topic}")

        return load_result

    def _ros_message_to_dict(self, message: Any) -> Dict:
        """
        任意のROSメッセージオブジェクトを再帰的に辞書型に変換する汎用関数

        Args:
            message: 変換するROSメッセージオブジェクト

        Returns:
            Dict: メッセージを表す辞書
        """
        if message is None:
            return None

        # プリミティブ型の処理
        if isinstance(message, (int, float, str, bool)):
            return message

        # numpy配列やリストの処理
        if isinstance(message, (list, tuple)) or hasattr(message, '__iter__') and not isinstance(message, (str, dict, bytes)):
            try:
                return [self._ros_message_to_dict(item) for item in message]
            except TypeError:
                # iter可能だがイテレーションが失敗した場合
                pass

        # numpy型の処理
        if hasattr(message, 'dtype') and hasattr(message, 'tolist'):
            return message.tolist()  # numpy配列をリストに変換

        # バイナリデータの処理
        if isinstance(message, bytes):
            return message.hex()  # 16進数文字列として保存

        # 辞書型の処理
        if isinstance(message, dict):
            return {k: self._ros_message_to_dict(v) for k, v in message.items()}

        # 他のオブジェクトの処理 (おそらくROSメッセージ)
        result = {}

        # オブジェクトの属性を取得する方法の優先順位
        # 1. __slots__がある場合はそれを使用
        # 2. __dict__がある場合はそれを使用
        # 3. dir()関数を使用して全ての属性を取得

        attrs = []

        # __slots__属性がある場合はそれを使用
        if hasattr(message, '__slots__'):
            attrs = message.__slots__
        # __dict__属性がある場合はそれを使用
        elif hasattr(message, '__dict__'):
            attrs = message.__dict__.keys()
        else:
            # 全ての属性を取得（但し、"_"で始まる内部属性は除外）
            attrs = [attr for attr in dir(message) if not attr.startswith('_') and not inspect.ismethod(getattr(message, attr))]

        # 各属性を処理
        for attr in attrs:
            try:
                value = getattr(message, attr)
                # メソッドやプロパティは無視
                if not callable(value):
                    result[attr] = self._ros_message_to_dict(value)
            except Exception as e:
                # 属性にアクセスできない場合はスキップ
                result[attr] = f"<Error accessing: {str(e)}>"

        return result

    def _to_nanoseconds(self, msg):
        if "header" not in msg:
            return 0

        stamp = msg["header"]["stamp"]
        # secs = stamp["secs"]
        # nsecs = stamp["nsecs"]
        secs = stamp["sec"]
        nsecs = stamp["nanosec"]
        return secs * 1_000_000_000 + nsecs
