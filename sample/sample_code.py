from mcapture.mcap_loader import McapLoader
from mcapture.synchronizer import Synchronizer, SyncMethod

import os


def main():
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

    # 同期方式を選択 EXACT_TIME, APPROXIMATE_TIME, APPROXIMATE_EPSILON_TIME, LATEST_TIME
    sync_method = SyncMethod.APPROXIMATE_EPSILON_TIME

    # 同期器を作成
    synchronizer = Synchronizer(
        sync_method=sync_method,
        time_tolerance=0.05,         # 70ミリ秒
        base_topic=target_topics[1]  # ApproximateTimeで使用するベーストピック
    )

    synchronize_result = synchronizer.synchronize(load_result)
    synchronizer.plot(synchronize_result, target_topics)


if __name__ == "__main__":
    main()
