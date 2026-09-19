"""三地市场的指数、板块与成分标的。可随时增删。

代码约定：
- 美股：雅虎代码（NVDA、^GSPC、ES=F）
- 港股 / A股：腾讯行情代码（hk00700、hkHSI、sh512480、sz300308）
"""
from dataclasses import dataclass, field


@dataclass
class Group:
    name: str
    members: dict[str, str]  # code -> 显示名
    focus: bool = False  # 属于 AI 科技 / 半导体重点板块


@dataclass
class Market:
    key: str  # US / HK / CN
    name: str
    indices: dict[str, str]
    groups: list[Group] = field(default_factory=list)
    context: dict[str, str] = field(default_factory=dict)  # 期货、利率等背景指标


US = Market(
    key="US",
    name="美股",
    indices={
        "^GSPC": "标普500",
        "^IXIC": "纳斯达克综指",
        "^DJI": "道琼斯",
        "^RUT": "罗素2000",
        "^SOX": "费城半导体",
    },
    context={
        "ES=F": "标普期货",
        "NQ=F": "纳指期货",
        "^VIX": "VIX",
        "^TNX": "10年美债收益率",
        "DX-Y.NYB": "美元指数",
        "GC=F": "黄金期货",
        "CL=F": "原油期货",
    },
    groups=[
        Group("AI/半导体基准ETF", {"SMH": "SMH 半导体ETF", "SOXX": "SOXX 半导体ETF", "IGV": "IGV 软件ETF"}, True),
        Group("算力GPU", {"NVDA": "英伟达", "AMD": "AMD"}, True),
        Group("定制ASIC/互连芯片", {"AVGO": "博通", "MRVL": "迈威尔", "ALAB": "Astera Labs", "CRDO": "Credo"}, True),
        Group("存储/HBM", {"MU": "美光", "WDC": "西部数据", "SNDK": "闪迪", "STX": "希捷"}, True),
        Group("晶圆代工/IDM", {"TSM": "台积电", "INTC": "英特尔", "GFS": "格芯"}, True),
        Group("半导体设备", {"ASML": "阿斯麦", "AMAT": "应用材料", "LRCX": "泛林", "KLAC": "科磊", "TER": "泰瑞达"}, True),
        Group("EDA/IP", {"SNPS": "新思科技", "CDNS": "楷登电子", "ARM": "Arm"}, True),
        Group("光互连/网络", {"ANET": "Arista", "COHR": "Coherent", "LITE": "Lumentum", "CIEN": "Ciena"}, True),
        Group("AI服务器", {"SMCI": "超微电脑", "DELL": "戴尔", "HPE": "慧与"}, True),
        Group("AI电力/散热", {"VRT": "维谛", "ETN": "伊顿", "GEV": "GE Vernova", "CEG": "Constellation", "VST": "Vistra"}, True),
        Group("云/超大规模", {"MSFT": "微软", "GOOGL": "谷歌", "AMZN": "亚马逊", "META": "Meta", "ORCL": "甲骨文", "CRWV": "CoreWeave"}, True),
        Group("AI软件/应用", {"PLTR": "Palantir", "NOW": "ServiceNow", "SNOW": "Snowflake", "APP": "AppLovin"}, True),
        Group("模拟/其他半导体", {"TXN": "德州仪器", "ADI": "亚德诺", "QCOM": "高通", "ON": "安森美", "NXPI": "恩智浦"}, True),
        Group("行业ETF", {
            "XLK": "科技", "XLC": "通信服务", "XLY": "可选消费", "XLP": "必需消费", "XLV": "医疗保健",
            "XLF": "金融", "XLE": "能源", "XLI": "工业", "XLB": "材料", "XLU": "公用事业", "XLRE": "房地产",
        }),
        Group("主题ETF", {
            "XBI": "生物科技", "KRE": "地区银行", "ITA": "航空国防", "URA": "铀/核能", "TAN": "太阳能",
            "LIT": "锂电", "COPX": "铜矿", "GDX": "金矿", "SLV": "白银", "IBIT": "比特币",
            "KWEB": "中概互联网", "IWM": "小盘股", "CIBR": "网络安全", "BOTZ": "机器人", "UFO": "太空",
            "XHB": "住宅建筑", "XRT": "零售", "JETS": "航空",
        }),
    ],
)

HK = Market(
    key="HK",
    name="港股",
    indices={"hkHSI": "恒生指数", "hkHSTECH": "恒生科技", "hkHSCEI": "国企指数"},
    groups=[
        Group("互联网/AI平台", {
            "hk00700": "腾讯控股", "hk09988": "阿里巴巴", "hk03690": "美团", "hk09618": "京东集团",
            "hk01024": "快手", "hk09888": "百度集团",
        }, True),
        Group("半导体", {"hk00981": "中芯国际", "hk01347": "华虹半导体", "hk00522": "ASMPT"}, True),
        Group("AI硬件/消费电子", {"hk01810": "小米集团", "hk00992": "联想集团", "hk02382": "舜宇光学", "hk00285": "比亚迪电子"}, True),
        Group("新能源车", {"hk01211": "比亚迪股份", "hk02015": "理想汽车", "hk09868": "小鹏汽车", "hk09866": "蔚来", "hk00175": "吉利汽车"}),
        Group("创新药/医药", {"hk01801": "信达生物", "hk06160": "百济神州", "hk09926": "康方生物", "hk01177": "中国生物制药", "hk02269": "药明生物"}),
        Group("新消费", {"hk09992": "泡泡玛特", "hk02020": "安踏体育", "hk09633": "农夫山泉", "hk06862": "海底捞"}),
        Group("金融", {"hk00005": "汇丰控股", "hk01299": "友邦保险", "hk00388": "香港交易所", "hk02318": "中国平安"}),
        Group("资源/能源", {"hk00883": "中国海洋石油", "hk02899": "紫金矿业", "hk00857": "中国石油股份"}),
    ],
)

CN = Market(
    key="CN",
    name="A股",
    indices={
        "sh000001": "上证指数", "sz399001": "深证成指", "sz399006": "创业板指",
        "sh000688": "科创50", "sh000300": "沪深300",
    },
    groups=[
        Group("半导体/芯片", {"sh512480": "半导体ETF", "sz159995": "芯片ETF", "sh588200": "科创芯片ETF", "sz159516": "半导体设备ETF"}, True),
        Group("人工智能", {"sh515070": "人工智能AIETF", "sz159819": "人工智能ETF"}, True),
        Group("通信/光模块", {"sh515880": "通信ETF"}, True),
        Group("计算机/软件", {"sh512720": "计算机ETF", "sz159852": "软件ETF"}, True),
        Group("消费电子/机器人", {"sz159732": "消费电子ETF", "sh562500": "机器人ETF"}, True),
        Group("A股AI/半导体龙头", {
            "sh688981": "中芯国际", "sh688256": "寒武纪", "sz002371": "北方华创", "sh688012": "中微公司",
            "sh688041": "海光信息", "sh688008": "澜起科技", "sh603986": "兆易创新", "sz300308": "中际旭创",
            "sz300502": "新易盛", "sh601138": "工业富联", "sz002463": "沪电股份", "sz300476": "胜宏科技",
            "sz000977": "浪潮信息", "sz002230": "科大讯飞", "sh688111": "金山办公",
        }, True),
        Group("传媒/游戏", {"sz159869": "游戏ETF", "sh512980": "传媒ETF"}),
        Group("医药", {"sh512010": "医药ETF", "sz159992": "创新药ETF", "sz159883": "医疗器械ETF"}),
        Group("消费", {"sz159928": "消费ETF", "sh512690": "酒ETF"}),
        Group("金融", {"sh512880": "证券ETF", "sh512800": "银行ETF"}),
        Group("新能源", {"sh515030": "新能源车ETF", "sz159755": "电池ETF", "sh515790": "光伏ETF"}),
        Group("周期/资源", {
            "sh512400": "有色金属ETF", "sh516150": "稀土ETF", "sh518880": "黄金ETF",
            "sh515220": "煤炭ETF", "sz159870": "化工ETF",
        }),
        Group("其他", {"sh512660": "军工ETF", "sz159611": "电力ETF", "sh512200": "房地产ETF"}),
    ],
)

MARKETS = {"US": US, "HK": HK, "CN": CN}

# 判断当日是否开市用的代表指数
GATE_INDEX = {"US": "^GSPC", "HK": "hkHSI", "CN": "sh000001"}


def all_codes(market: Market) -> dict[str, str]:
    codes = dict(market.indices)
    codes.update(market.context)
    for g in market.groups:
        codes.update(g.members)
    return codes
