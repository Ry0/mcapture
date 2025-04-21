# Mcapture
This module provides functionalities to load MCAP files saved using ROS2's rosbag feature and convert them into standard Python dictionaries. It also offers a feature to synchronize multimodal data based on timestamps (emulating ROS2's message filters functionality).

## Features
### Load MCAP Files

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
### Time Synchronization for Multimodal Data

Supports the following four synchronization methods:

> [!IMPORTANT]
> This is not a complete reproduction of ROS2's message filters feature.
> Some behavior is based on custom interpretation.

* `ExactTime`: Synchronizes only messages with exactly the same timestamp
* `ApproximateTime`（currently being implemented）: Finds the best match of temporally close messages
* `ApproximateEpsilonTime`（currently being implemented）: Synchronizes messages within a specified time window
* `LatestTime`: Samples at regular intervals and uses the latest available messages

```python
from synchronizer import Synchronizer

# Create synchronizer instance
sync = Synchronizer()

# Prepare data (from McapLoader)
data = {
    "/joint_states": [message_list_1],
    "/camera/camera/color/image_rect_raw": [message_list_2],
    "/image_raw": [message_list_3]
}

# Select synchronization method

# 1. ExactTime Synchronization
exact_sync_data = sync.synchronize_exact_time(data)

# 2. ApproximateTime Synchronization
approx_sync_data = sync.synchronize_approximate_time(data, queue_size=100)

# 3. ApproximateEpsilonTime Synchronization
epsilon_sync_data = sync.synchronize_approximate_epsilon_time(data, epsilon_sec=0.1)

# 4. LatestTime Synchronization
latest_sync_data = sync.synchronize_latest_time(data, sampling_interval_sec=0.1)
```

### Visualization of Synchronized Data

```python
# Visualize synchronization results
target_topics = [
    "/joint_states",
    "/camera/camera/color/image_rect_raw",
    "/image_raw"
]
sync.plot(exact_sync_data, target_topics)
```

## Sample Data
You can find a sample dataset on [Google Drive](https://drive.google.com/file/d/19syK1ukBqSF0Aje4-crzr3pdAnfyz1X2/view)においています。

https://github.com/user-attachments/assets/aa9e488c-6b3d-43d2-ab50-1bee820c6ec2


## Overview of Synchronization Algorithms
### ExactTime
Synchronizes only messages that share the exact same timestamp. A synchronized dataframe is only created when all topics have messages with matching timestamps.

![Image](https://github.com/user-attachments/assets/7a9d93e5-2ebc-4c44-b629-d6f71f5eebb4)

> [!NOTE]
> The above image is from dummy data. The sample dataset does not contain perfectly matching timestamps.

### ApproximateTime（currently being implemented）
Finds the optimal combination of temporally close messages. Messages from each topic are stored in queues, and the combination with the minimum timestamp difference is selected.

![Image](https://github.com/user-attachments/assets/549acd5e-9e9e-4903-a65b-8f133ea20e9b)

### ApproximateEpsilonTime（currently being implemented）
Synchronizes messages that fall within a user-defined time window (epsilon). If the time difference between the head messages of each topic is within the epsilon threshold, they are synchronized.

![Image](https://github.com/user-attachments/assets/1d8e86d6-c5d8-4fe3-a500-c7ea8e88af1a)

### LatestTime
Samples data at regular time intervals, using the latest available message from each topic at each sampling point.

![Image](https://github.com/user-attachments/assets/9e87907d-f1ee-4213-8cd8-733bb253b2b5)

## License
MIT Lisence
