from mcapture.mcap_loader import McapLoader
from mcapture.synchronizer import Synchronizer

import os


def main():
    base_path = os.path.dirname(os.path.abspath(__file__))
    mcap_file_name = "rosbag2_2025_04_20-16_32_05/rosbag2_2025_04_20-16_32_05_0.mcap"
    mcap_file_path = os.path.join(base_path, "data", mcap_file_name)

    target_topics = [
        "/joint_states",
        "/camera/camera/color/image_rect_raw",
        "/image_raw"
        # "/camera/camera/depth/image_rect_raw",
    ]

    loader = McapLoader()
    load_result = loader.load_mcap(mcap_file_path, target_topics)

    print(f"Topic list: {load_result.keys()}")
    for key in load_result:
        print(f"Topic name: {key}, Data length: {len(load_result[key])}")

    # 同期器を作成
    synchronizer = Synchronizer()

    # synchronize_result = synchronizer.synchronize_approximate_time(load_result, 100, 10, 0.1)
    # synchronize_result = synchronizer.synchronize_approximate_epsilon_time(load_result)
    synchronize_result = synchronizer.synchronize_latest_time(load_result, 0.1)
    synchronizer.plot(synchronize_result, target_topics)


if __name__ == "__main__":
    main()
