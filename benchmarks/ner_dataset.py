from __future__ import annotations


def _sample(text: str, labels: list[tuple[str, str]]) -> dict:
    entities = []
    cursors: dict[str, int] = {}
    for category, value in labels:
        start = text.index(value, cursors.get(value, 0))
        end = start + len(value)
        cursors[value] = end
        entities.append({"category": category, "start": start, "end": end, "text": value})
    return {"text": text, "entities": entities}


def samples() -> list[dict]:
    long_prefix = "系统运行正常，无敏感实体。" * 60
    long_text = long_prefix + "边界位置由顾清扬提交给星澜科技有限公司。" + "任务继续执行。" * 60 + "末尾联系人欧阳澈"
    rows = [
        _sample("负责人韩静提交了故障记录。", [("PERSON", "韩静")]),
        _sample("顾清扬和欧阳澈共同复核需求。", [("PERSON", "顾清扬"), ("PERSON", "欧阳澈")]),
        _sample("星澜科技有限公司向海川大学发送了测试报告。", [("ORG", "星澜科技有限公司"), ("ORG", "海川大学")]),
        _sample("临江市数据管理局发布了接口变更通知。", [("ORG", "临江市数据管理局")]),
        _sample("星河门户升级项目由星澜科技有限公司负责实施。", [("ORG", "星澜科技有限公司")]),
        _sample("日志：韩静登录失败，随后韩静重新认证成功。", [("PERSON", "韩静"), ("PERSON", "韩静")]),
        _sample("SELECT * FROM audit_log WHERE operator='顾清扬';", [("PERSON", "顾清扬")]),
        _sample('{"owner":"欧阳澈","organization":"海川大学"}', [("PERSON", "欧阳澈"), ("ORG", "海川大学")]),
        _sample("工单反馈：临江市数据管理局的陈默无法访问系统。", [("ORG", "临江市数据管理局"), ("PERSON", "陈默")]),
        _sample("需求要求由海川大学确认验收范围，星河门户升级项目不是组织名称。", [("ORG", "海川大学")]),
        _sample("访问 https://internal.example.com 后查询 user_account 表，服务器为10.0.0.1。", []),
        _sample("password=zhangsan123，token=abcdef123456，任务执行正常。", []),
        _sample("本段文本没有人名或组织机构，仅描述普通系统状态。", []),
        _sample(long_text, [("PERSON", "顾清扬"), ("ORG", "星澜科技有限公司"), ("PERSON", "欧阳澈")]),
    ]
    positive_pairs = [
        ("林涛", "云栖数据有限公司"), ("周宁", "北辰大学"), ("赵敏", "澄江市政务服务局"),
        ("钱峰", "启明材料研究院"), ("孙悦", "远航网络有限公司"), ("李珊", "南岭理工大学"),
        ("吴昊", "安澜市信息中心"), ("郑凯", "青禾人工智能研究院"), ("王璐", "微光软件有限公司"),
        ("冯雪", "东川财经大学"), ("陈默", "临海市档案馆"), ("褚航", "博远技术研究院"),
        ("卫然", "青云系统有限公司"), ("蒋欣", "西河交通大学"), ("沈卓", "新港市数据资源局"),
        ("韩冬", "天穹安全研究院"), ("杨柳", "澜舟科技有限公司"), ("朱晨", "华岭师范大学"),
        ("秦川", "松江市审计局"), ("许安", "镜湖计算技术研究院"), ("欧阳澈", "星澜科技有限公司"),
        ("司马宁", "海川大学"), ("上官悦", "临江市数据管理局"), ("顾清扬", "云帆工业研究院"),
        ("陆星河", "白鹭软件有限公司"),
    ]
    templates = [
        "日志记录：{person}代表{org}提交了异常报告。",
        "工单内容：请联系{org}的{person}确认处理结果。",
        '{{"owner":"{person}","organization":"{org}"}}',
        "SELECT * FROM audit_log WHERE operator='{person}'; -- 所属机构：{org}",
        "需求说明：{org}负责验收，接口联系人为{person}。",
    ]
    for index, (person, organization) in enumerate(positive_pairs):
        text = templates[index % len(templates)].format(person=person, org=organization)
        rows.append(_sample(text, [("PERSON", person), ("ORG", organization)]))
    negatives = [
        "GET https://api.example.test/v1/users 返回 500。", "服务器10.0.0.8无法连接数据库。",
        "SELECT id, user_name FROM account_table WHERE enabled=1;", '{"project":"星河门户升级项目","status":"running"}',
        "Authorization: Bearer abcdef1234567890", "password=test123456; secret=local_only",
        "Spring Boot application started in 2.3 seconds.", "NullPointerException at ServiceImpl.java:42",
        "Redis connection pool exhausted, retry after 500ms.", "字段 customer_name 长度由64调整为128。",
        "项目名称是数据治理二期，不代表任何组织机构。", "Chrome、Python、PostgreSQL 均为技术名词。",
        "访问 internal.example.test 后执行健康检查。", "订单编号A20260920001处理完成。",
        "CPU 35%，内存占用512MB，磁盘空间充足。", "表 audit_log 与字段 operator_id 已建立索引。",
        "本条工单没有联系人，也没有客户或组织名称。",
    ]
    rows.extend(_sample(text, []) for text in negatives)
    return rows
