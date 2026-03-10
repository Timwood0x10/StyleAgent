"""
Ethereum Node Query Utilities - 查询以太坊节点状态数据

提供功能：
- 连接以太坊节点
- 查询区块范围的状态数据
- 获取当前区块高度
- 批量查询区块信息
"""

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from web3 import Web3
from web3.exceptions import BlockNotFound

from .config import Config
from . import get_logger

logger = get_logger(__name__)

# 全局配置实例
config = Config()


@dataclass
class BlockInfo:
    """区块信息"""
    number: int
    hash: str
    timestamp: int
    gas_used: int
    gas_limit: int
    transaction_count: int
    parent_hash: str


class ETHNodeClient:
    """以太坊节点客户端"""

    def __init__(self, rpc_url: Optional[str] = None, network: str = "mainnet"):
        """
        初始化 ETH 节点客户端

        Args:
            rpc_url: RPC URL，如果为 None 则从配置读取
            network: 网络名称 (mainnet, sepolia, goerli)
        """
        self.rpc_url = rpc_url or config.ETH_RPC_URL or os.getenv("ETH_RPC_URL", "")
        self.network = network
        self.w3: Optional[Web3] = None

        if self.rpc_url:
            self._connect()
        else:
            logger.warning("ETH RPC URL 未配置")

    def _connect(self):
        """连接到以太坊节点"""
        try:
            self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))
            if self.w3.is_connected():
                logger.info(f"成功连接到 {self.network} 网络")
            else:
                logger.error(f"无法连接到 {self.network} 网络")
                self.w3 = None
        except Exception as e:
            logger.error(f"连接以太坊节点失败: {e}")
            self.w3 = None

    @property
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self.w3 is not None and self.w3.is_connected()

    def get_current_block_number(self) -> int:
        """获取当前最新区块高度"""
        if not self.is_connected:
            raise ConnectionError("未连接到以太坊节点")
        return self.w3.eth.block_number

    def get_block_by_number(self, block_number: int) -> Optional[BlockInfo]:
        """
        根据区块高度获取区块信息

        Args:
            block_number: 区块高度

        Returns:
            BlockInfo 对象，如果区块不存在则返回 None
        """
        if not self.is_connected:
            raise ConnectionError("未连接到以太坊节点")

        try:
            block = self.w3.eth.get_block(block_number)
            return BlockInfo(
                number=block.number,
                hash=block.hash.hex(),
                timestamp=block.timestamp,
                gas_used=block.gas_used,
                gas_limit=block.gas_limit,
                transaction_count=len(block.transactions),
                parent_hash=block.parent_hash.hex(),
            )
        except BlockNotFound:
            logger.warning(f"区块 {block_number} 不存在")
            return None
        except Exception as e:
            logger.error(f"获取区块 {block_number} 失败: {e}")
            return None

    def get_state_at_block(self, block_number: int) -> Dict[str, Any]:
        """
        获取指定区块的状态数据

        Args:
            block_number: 区块高度

        Returns:
            包含状态数据的字典
        """
        if not self.is_connected:
            raise ConnectionError("未连接到以太坊节点")

        try:
            block = self.w3.eth.get_block(block_number, full_transactions=False)
            return {
                "block_number": block.number,
                "block_hash": block.hash.hex(),
                "parent_hash": block.parent_hash.hex(),
                "timestamp": block.timestamp,
                "gas_used": block.gas_used,
                "gas_limit": block.gas_limit,
                "transaction_count": len(block.transactions),
                "difficulty": block.difficulty,
                "total_difficulty": block.total_difficulty,
                "miner": block.miner,
                "size": block.size,
            }
        except Exception as e:
            logger.error(f"获取区块 {block_number} 状态失败: {e}")
            return {"error": str(e)}


class ETHStateRangeQuery:
    """以太坊状态范围查询"""

    def __init__(self, rpc_url: Optional[str] = None, network: str = "mainnet"):
        self.client = ETHNodeClient(rpc_url, network)

    def query_range(
        self,
        start_block: int = 0,
        end_block: int = 0,
        batch_size: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        查询区块范围的状态数据

        Args:
            start_block: 起始区块高度
            end_block: 结束区块高度，0 表示查询到最新区块
            batch_size: 每次查询的批次大小

        Returns:
            区块状态数据列表
        """
        if not self.client.is_connected:
            raise ConnectionError("未连接到以太坊节点")

        # 确定实际结束区块
        if end_block == 0:
            end_block = self.client.get_current_block_number()

        # 验证起始区块
        if start_block < 0:
            raise ValueError("起始区块高度不能为负数")
        if start_block > end_block:
            raise ValueError("起始区块高度不能大于结束区块高度")

        results = []
        current = start_block

        logger.info(f"开始查询区块范围: {start_block} - {end_block}")

        while current <= end_block:
            # 计算当前批次大小
            batch_end = min(current + batch_size - 1, end_block)

            # 查询批次
            for block_num in range(current, batch_end + 1):
                state = self.client.get_state_at_block(block_num)
                if state and "error" not in state:
                    results.append(state)

            logger.info(f"已查询 {len(results)} / {end_block - start_block + 1} 个区块")
            current = batch_end + 1

        return results

    def get_start_height(self, custom_start: Optional[int] = None) -> int:
        """
        获取状态数据的起始高度

        Args:
            custom_start: 自定义起始高度，如果为 None 则从配置读取

        Returns:
            实际的起始区块高度
        """
        if custom_start is not None:
            return custom_start

        # 从配置读取
        config_start = config.ETH_START_BLOCK
        if config_start > 0:
            return config_start

        # 默认从创世区块开始
        return 0


class ETHSnapshotFinder:
    """
    以太坊快照起始高度查找器 - 使用二分法快速定位节点数据的起始高度

    用于确定快照节点是从哪个区块高度开始同步的
    """

    # 常用测试地址（以太坊创始人地址）
    TEST_ADDRESS = "0x0000000000000000000000000000000000000000"

    def __init__(self, rpc_url: Optional[str] = None, network: str = "mainnet"):
        self.client = ETHNodeClient(rpc_url, network)

    def check_block_exists(self, block_number: int) -> bool:
        """
        检查指定区块是否存在（可访问）

        Args:
            block_number: 区块高度

        Returns:
            True 表示区块存在/可访问，False 表示不存在
        """
        try:
            if not self.client.is_connected:
                return False
            # 尝试获取区块头，如果不存在会抛出异常
            self.client.w3.eth.get_block(block_number)
            return True
        except BlockNotFound:
            return False
        except Exception:
            return False

    def check_state_exists(self, block_number: int) -> bool:
        """
        检查指定区块的状态数据是否存在（可查询）

        使用 eth_getBalance 测试节点是否支持查询该高度的状态
        以太坊节点默认只保留最近 128 个区块的完整状态

        Args:
            block_number: 区块高度

        Returns:
            True 表示状态数据存在/可查询，False 表示状态不可用
        """
        try:
            if not self.client.is_connected:
                return False
            # 尝试获取某个地址在该区块的余额
            # 如果状态不可用，会抛出异常或返回错误
            balance = self.client.w3.eth.get_balance(
                self.TEST_ADDRESS, block_identifier=block_number
            )
            return True  # 如果没抛异常，说明状态可查询
        except Exception as e:
            error_msg = str(e).lower()
            # 常见的错误关键词
            if any(kw in error_msg for kw in ["not found", "unknown block", "invalid"]):
                return False
            # 其他错误也视为状态不可用
            return False

    def find_state_start_height(
        self,
        max_iterations: int = 30,
        early_exit_block: int = 0,
    ) -> Dict[str, Any]:
        """
        使用二分法快速查找快照节点状态数据的起始高度

        以太坊节点通常只保留近期区块的完整状态（如最近128个区块）
        更早的区块可能只有区块头数据，没有账户余额、合约存储等状态

        Args:
            max_iterations: 最大迭代次数
            early_exit_block: 提前终止的参考区块

        Returns:
            包含查找结果的字典：
            - found: 是否找到起始高度
            - state_start_height: 状态数据起始高度
            - current_block: 当前最新区块高度
            - iterations: 迭代次数
            - message: 描述信息
        """
        if not self.client.is_connected:
            return {
                "found": False,
                "error": "未连接到以太坊节点",
                "connected": False,
            }

        current_block = self.client.get_current_block_number()

        # 先测试当前区块是否有状态（确认节点正常工作）
        if not self.check_state_exists(current_block):
            return {
                "found": False,
                "error": "当前区块状态不可用，节点可能异常",
                "current_block": current_block,
            }

        # 二分查找：从 [0, current_block] 找到状态数据的起始高度
        left = 0
        right = current_block

        iterations = 0
        while iterations < max_iterations and left < right:
            mid = (left + right) // 2
            iterations += 1

            if self.check_state_exists(mid):
                # 状态存在，向前继续查找更早的
                right = mid
            else:
                # 状态不存在，向后查找
                left = mid + 1

        found_height = left

        # 验证结果
        if found_height == 0:
            # 再确认一下区块0是否真的有状态
            if self.check_state_exists(0):
                return {
                    "found": True,
                    "state_start_height": 0,
                    "current_block": current_block,
                    "iterations": iterations,
                    "message": "状态数据从创世区块开始（archive节点）",
                }

        # 检查边界情况：found_height 有状态，但 found_height-1 没有状态
        if self.check_state_exists(found_height):
            if found_height > 0 and not self.check_state_exists(found_height - 1):
                return {
                    "found": True,
                    "state_start_height": found_height,
                    "current_block": current_block,
                    "iterations": iterations,
                    "message": f"状态数据起始高度: {found_height}",
                }
            elif found_height == 0:
                return {
                    "found": True,
                    "state_start_height": 0,
                    "current_block": current_block,
                    "iterations": iterations,
                    "message": "状态数据从创世区块开始",
                }
            else:
                # 前后都有状态，继续向前找真正的边界
                while found_height > 0 and self.check_state_exists(found_height - 1):
                    found_height -= 1

                return {
                    "found": True,
                    "state_start_height": found_height,
                    "current_block": current_block,
                    "iterations": iterations,
                    "message": f"状态数据起始高度: {found_height}",
                }
        else:
            return {
                "found": True,
                "state_start_height": found_height,
                "current_block": current_block,
                "iterations": iterations,
                "message": f"状态数据起始高度: {found_height}",
            }

    def find_snapshot_start_height(
        self,
        max_iterations: int = 20,
        early_exit_block: int = 0,
    ) -> Dict[str, Any]:
        """
        使用二分法快速查找快照节点的起始高度

        算法：
        1. 先检查创世区块(0)是否存在
        2. 如果不存在，获取当前最新区块高度
        3. 在 [0, current_block] 范围内使用二分查找
        4. 找到第一个存在且前一个区块不存在的位置

        Args:
            max_iterations: 最大迭代次数（默认20次足以覆盖以太坊全部区块）
            early_exit_block: 提前终止查找的参考区块（用于优化）

        Returns:
            包含查找结果的字典：
            - found: 是否找到起始高度
            - start_height: 快照起始高度（能获取数据的最旧区块）
            - current_block: 当前最新区块高度
            - iterations: 迭代次数
            - message: 描述信息
        """
        if not self.client.is_connected:
            return {
                "found": False,
                "error": "未连接到以太坊节点",
                "connected": False,
            }

        current_block = self.client.get_current_block_number()

        # 先检查创世区块
        if self.check_block_exists(0):
            return {
                "found": True,
                "start_height": 0,
                "current_block": current_block,
                "iterations": 0,
                "message": "节点包含创世区块（从区块0开始）",
            }

        # 使用二分查找
        left = 0
        right = current_block
        iterations = 0

        # 优化：如果有早期退出区块，优先检查该区块
        if early_exit_block > 0 and early_exit_block < current_block:
            if not self.check_block_exists(early_exit_block):
                # early_exit_block 不存在，说明快照在此之后
                right = current_block
                left = early_exit_block
            else:
                # early_exit_block 存在，进一步向前查找
                right = early_exit_block

        while iterations < max_iterations and left < right:
            mid = (left + right) // 2
            iterations += 1

            if self.check_block_exists(mid):
                # 中间区块存在，说明起始点在 mid 之前
                right = mid
            else:
                # 中间区块不存在，说明起始点在 mid 之后
                left = mid + 1

        # 验证找到的位置
        found_height = left

        # 检查找到的区块是否真的存在
        if self.check_block_exists(found_height):
            # 检查前一个区块是否不存在
            if found_height == 0:
                prev_exists = False
            else:
                prev_exists = self.check_block_exists(found_height - 1)

            if not prev_exists or found_height == 0:
                return {
                    "found": True,
                    "start_height": found_height,
                    "current_block": current_block,
                    "iterations": iterations,
                    "message": f"快照起始高度: {found_height}",
                }
            else:
                # 找到的位置前一个区块也存在，继续向前查找
                left = found_height
                right = found_height
                while self.check_block_exists(left - 1):
                    left -= 1
                    iterations += 1

                return {
                    "found": True,
                    "start_height": left,
                    "current_block": current_block,
                    "iterations": iterations,
                    "message": f"快照起始高度: {left}",
                }
        else:
            return {
                "found": False,
                "error": f"无法确定起始高度，可能节点数据异常",
                "current_block": current_block,
                "iterations": iterations,
            }


def get_eth_state_data(
    rpc_url: Optional[str] = None,
    start_block: Optional[int] = None,
    end_block: int = 0,
    network: str = "mainnet",
) -> Dict[str, Any]:
    """
    便捷函数：获取以太坊节点状态数据

    Args:
        rpc_url: RPC URL
        start_block: 起始区块高度，None 则从配置读取
        end_block: 结束区块高度，0 表示最新区块
        network: 网络名称

    Returns:
        包含状态数据和元信息的字典
    """
    query = ETHStateRangeQuery(rpc_url=rpc_url, network=network)

    if not query.client.is_connected:
        return {
            "error": "无法连接到以太坊节点",
            "connected": False,
        }

    # 确定起始高度
    actual_start = query.get_start_height(start_block)

    # 获取当前最新区块
    current_block = query.client.get_current_block_number()

    # 如果 end_block 为 0，使用当前区块
    actual_end = end_block if end_block > 0 else current_block

    # 查询数据
    states = query.query_range(actual_start, actual_end)

    return {
        "connected": True,
        "network": network,
        "current_block": current_block,
        "start_block": actual_start,
        "end_block": actual_end,
        "total_blocks": len(states),
        "states": states,
    }


# 示例用法
if __name__ == "__main__":
    import json

    # 使用用户提供的 ZAN API
    rpc_url = "https://api.zan.top/node/v1/eth/mainnet/f49b1672f41f49d2b0ba6dfc92a831de"

    # ========== 示例1: 查询当前区块高度 ==========
    client = ETHNodeClient(rpc_url)
    if client.is_connected:
        print(f"当前区块高度: {client.get_current_block_number()}")

        # 查询特定区块的状态
        block_info = client.get_block_by_number(19000000)
        if block_info:
            print(f"区块信息: {block_info}")

        # 查询区块范围
        query = ETHStateRangeQuery(rpc_url)
        states = query.query_range(19000000, 19000010)
        print(f"查询到 {len(states)} 个区块的状态数据")
    else:
        print("无法连接到以太坊节点")

    # ========== 示例2: 使用二分法查找快照起始高度 ==========
    print("\n" + "=" * 50)
    print("开始二分查找快照起始高度...")
    print("=" * 50)

    finder = ETHSnapshotFinder(rpc_url)
    result = finder.find_snapshot_start_height()

    if result.get("found"):
        print(f"✅ 找到快照起始高度: {result['start_height']}")
        print(f"   当前区块高度: {result['current_block']}")
        print(f"   迭代次数: {result['iterations']}")
        print(f"   信息: {result['message']}")
    else:
        print(f"❌ 查找失败: {result.get('error', '未知错误')}")
