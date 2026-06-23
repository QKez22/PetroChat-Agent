### 表 `add_time_task`

| 字段 | 类型 | 主键 | 可空 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | int | ✓ | N | 自增主键 |
| `task_id` | varchar(255) |  | Y | 唯一标识 |
| `operation_department` | varchar(255) |  | Y | 运行部 |
| `zz_name` | varchar(255) |  | Y | 装置 |
| `xxl_id` | int |  | Y | 关联xxl_id |
| `job_group` | int |  | N | 执行器id |
| `job_desc` | varchar(255) |  | N | 任务描述 |
| `add_time` | datetime |  | Y | 添加时间 |
| `update_time` | datetime |  | Y | 修改时间 |
| `author` | varchar(64) |  | Y | 作者 |
| `task_flag` | varchar(255) |  | Y | 任务标识 |
| `schedule_type` | varchar(50) |  | N | 调度类型 |
| `schedule_conf` | varchar(128) |  | Y | 调度配置，值含义取决于调度类型 |
| `executor_handler` | varchar(255) |  | Y | 执行器任务handler |
| `executor_param` | varchar(512) |  | Y | 执行器任务参数 |
| `glue_type` | varchar(50) |  | N | GLUE类型 |
| `glue_updatetime` | datetime |  | Y | GLUE更新时间 |
| `trigger_status` | tinyint |  | N | 调度状态：0-停止，1-运行，-1删除 |
| `operate_user` | varchar(255) |  | Y | 状态改变操作人 |

**列实际取值（来自当前数据，LLM 选 WHERE 字面量时务必从这里挑）：**
- `job_desc`：`测试`
- `author`：`lzx`
- `schedule_type`：`CRON`
- `schedule_conf`：`* * * * * ?`
- `executor_handler`：`test1`
- `executor_param`：`{78787778}`
- `glue_type`：`BEAN`

### 表 `affair`

| 字段 | 类型 | 主键 | 可空 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | int | ✓ | N |  |
| `affair_id` | varchar(255) |  | Y | 事务唯一性id |
| `specialty` | varchar(255) |  | Y | 专业 |
| `area` | varchar(255) |  | Y | 区域 |
| `affair_code` | varchar(255) |  | Y | 事务识别码 |
| `affair_name` | varchar(255) |  | Y | 事务名称 |
| `frequency` | varchar(255) |  | Y | 中韩频次 |
| `if_auto` | varchar(225) |  | Y | 触发形式 |
| `ticket_flag` | int |  | Y | 是否需要开票（0：是，1：否） |
| `affair_type` | varchar(255) |  | Y | 事务类型 |
| `execution_type` | varchar(255) |  | Y | 执行形式（线上执行，自动生成；线下执行，上传表单；线下执行，执行确认，无需上传表单） |
| `execution_department` | varchar(255) |  | Y | 执行部门 |
| `execution_role` | varchar(255) |  | Y | 执行角色 |
| `trigger_time` | varchar(255) |  | Y | 触发时间 |
| `deadline` | varchar(255) |  | Y | 截止时间 |
| `xxl_id` | int |  | Y | 关联xxl_id |
| `job_group` | int |  | Y | 执行器id |
| `job_desc` | varchar(255) |  | Y | 任务描述 |
| `schedule_conf` | varchar(128) |  | Y | 调度配置，值含义取决于调度类型 |
| `executor_handler` | varchar(255) |  | Y | 执行器任务handler |
| `executor_param` | varchar(512) |  | Y | 执行器任务参数 |
| `trigger_status` | tinyint |  | Y | 调度状态：0-停止，1-运行，-1删除 |
| `operate_time` | datetime |  | Y | 操作时间 |
| `operate_user` | varchar(255) |  | Y | 状态改变操作人 |
| `check_flag` | int |  | Y | 是否需要制定线上检查表单(0: 是，1：否) |
| `report_user` | varchar(255) |  | Y | 提报人 |
| `report_time` | datetime |  | Y | 提报时间 |
| `signature` | varchar(255) |  | Y | 审核签名 |
| `template_name` | varchar(255) |  | Y | 模版名 |
| `template_path` | varchar(255) |  | Y | 模版路径 |
| `job_content` | varchar(1255) |  | Y |  |
| `change_time` | varchar(1255) |  | Y |  |
| `new_trigger_time` | varchar(255) |  | Y | 统计最新的触发时间 |
| `next_trigger_time` | varchar(255) |  | Y | 统计下次触发时间，最低间隔为月 |
| `affair_level` | varchar(255) |  | Y | 事务级别（总部级、运行部级、专业级） |

**列实际取值（来自当前数据，LLM 选 WHERE 字面量时务必从这里挑）：**
- `specialty`：`仪` / `其他` / `动` / `电` / `综合` / `静`
- `area`：`乙烯` / `全厂` / `炼油`
- `frequency`：`1次/2年` / `1次/两年` / `1次/半年` / `1次/周` / `1次/四年` / `1次/季度` / `1次/年` / `1次/日` / `1次/月` / `1次/检修周期` / `2次/月` / `出厂超1年` / `及时` / `大修时` / `按法律规范、规程规定` / `按预防性维修计划执行`
- `if_auto`：`人工触发` / `自动触发`
- `affair_type`：`会议总结类` / `执行确认类` / `检查巡检类` / `维护活动类`
- `execution_type`：`线上执行，自动生成表单` / `线下执行，上传表单` / `线下执行，执行确认，无需上传表单`
- `job_desc`：`会议总结类` / `执行确认类` / `检查巡检类` / `维护活动类`
- `executor_handler`：`manualTimingHandler` / `manualTimingHandlerTicket`
- `trigger_status`：`1`
- `operate_user`：`付笙泰` / `周锦巧` / `沈忱` / `王聪` / `袁智胜` / `邓强华` / `金坦`
- `report_user`：`付笙泰` / `刘嵩` / `周锦巧` / `张杨` / `沈忱` / `王惟一` / `王聪` / `袁民拥` / `邓强华` / `金坦`
- `affair_level`：`总部级`

### 表 `affair_equip_defect`
> 静设备月度缺陷数据

| 字段 | 类型 | 主键 | 可空 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | int | ✓ | N |  |
| `task_pushed_id` | varchar(255) |  | Y | 触发任务ID(唯一性) |
| `task_id` | varchar(255) |  | Y | 任务ID |
| `associated_affair_id` | varchar(255) |  | Y | 关联事务Id |
| `defect_id` | varchar(255) |  | Y | 缺陷编号 |
| `area` | varchar(255) |  | Y | 区域 |
| `operation_department` | varchar(255) |  | Y | 运行部 |
| `specialty` | varchar(255) |  | Y | 专业 |
| `zz_name` | varchar(255) |  | Y | 装置名称 |
| `equipment_code` | varchar(255) |  | Y | 设备编码 |
| `equipment_name` | varchar(255) |  | Y | 设备名称 |
| `equipment_tag` | varchar(255) |  | Y | 设备位号 |
| `equipment_description` | varchar(255) |  | Y | 设备描述 |
| `defect_description` | varchar(4000) |  | Y | 缺陷描述 |
| `defect_phenomenon` | varchar(255) |  | Y | 缺陷现象 |
| `defect_phenomenon_concrete` | varchar(255) |  | Y | 缺陷现象具体 |
| `defect_reporter` | varchar(255) |  | Y | 缺陷提报人 |
| `defect_report_time` | datetime |  | Y | 缺陷提报时间 |
| `defect_state` | varchar(255) |  | Y | 缺陷状态 待处理 处理中 |
| `remarks` | varchar(255) |  | Y | 备注 |

### 表 `affair_month_status`
> 静设备管道容器月度状态

| 字段 | 类型 | 主键 | 可空 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | int | ✓ | N |  |
| `task_pushed_id` | varchar(255) |  | Y | 触发任务ID(唯一性) |
| `task_id` | varchar(255) |  | Y | 任务ID |
| `associated_affair_id` | varchar(255) |  | Y | 关联事务Id |
| `area` | varchar(255) |  | Y | 区域 |
| `operation_department` | varchar(255) |  | Y | 运行部 |
| `specialty` | varchar(255) |  | Y | 专业 |
| `zz_name` | varchar(255) |  | Y | 装置名称 |
| `equipment_code` | varchar(255) |  | Y | 设备编码 |
| `equipment_tag` | varchar(255) |  | Y | 设备位号 |
| `equipment_name` | varchar(255) |  | Y | 设备名称 |
| `equipment_description` | varchar(255) |  | Y | 设备描述 |
| `equipment_status` | varchar(255) |  | Y | 设备状态 正常 异常 |

### 表 `affair_pipeline`
> 静设备管道容器数据

| 字段 | 类型 | 主键 | 可空 | 含义 |
| --- | --- | --- | --- | --- |
| `equipment_code` | varchar(255) | ✓ | N | 设备编码 |
| `equipment_tag` | varchar(255) |  | Y | 设备位号 |
| `equipment_type` | varchar(255) |  | Y | 设备类型 管道 容器 |
| `area` | varchar(255) |  | Y | 区域 |
| `operation_department` | varchar(255) |  | Y | 运行部 |
| `equipment_name` | varchar(255) |  | Y | 设备名称 |
| `zz_name` | varchar(255) |  | Y | 装置名称 |

**列实际取值（来自当前数据，LLM 选 WHERE 字面量时务必从这里挑）：**
- `equipment_type`：`容器` / `管道`
- `area`：`化工` / `炼油`
- `operation_department`：`储运部` / `动力部` / `化工公用工程部` / `检验计量中心` / `炼油一部` / `炼油三部` / `炼油二部` / `炼油公用工程部` / `炼油四部` / `烯烃部` / `环氧芳烃部` / `聚烯烃一部` / `聚烯烃二部`

### 表 `affair_stat_summary`
> 统计汇总表，定期更新用于快速查询

| 字段 | 类型 | 主键 | 可空 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | int | ✓ | N |  |
| `operation_department` | varchar(255) |  | Y | 运行部 |
| `specialty` | varchar(255) |  | Y | 专业 |
| `totals` | int |  | Y | 事务总数 |
| `scheduled_transaction_count` | int |  | Y | 应触发事务数 |
| `triggered_transaction_count` | int |  | Y | 触发事务总数 |
| `completed_transaction_count` | int |  | Y | 事务完成数 |
| `completed_transaction_rate` | double |  | Y | 事务完成率 |
| `scheduled_task_count` | int |  | Y | 应触发任务数 |
| `triggered_task_count` | int |  | Y | 触发任务数 |
| `executed_task_count` | int |  | Y | 已执行任务数 |
| `pending_tasks_count` | int |  | Y | 待处理任务数 |
| `timeout_completed_count` | int |  | Y | 超时已完 |
| `overdue_pending_count` | int |  | Y | 超时未完 |
| `execution_task_rate` | double |  | Y | 任务执行率 |
| `time_dimension` | tinyint |  | Y | 时间维度（1年度、2月度） |
| `statistics_dimension` | tinyint |  | Y | 统计维度（1专业维度、2运行部维度） |
| `statistics_date` | varchar(255) |  | Y | 统计日期（YYYY或YYYY-MM格式） |
| `start_cal` | varchar(255) |  | Y | 开始时间或年份 |
| `end_cal` | varchar(255) |  | Y | 结束时间 |
| `update_time` | datetime |  | Y | 更新时间 |

### 表 `affair_task`

| 字段 | 类型 | 主键 | 可空 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | int | ✓ | N |  |
| `task_id` | varchar(255) |  | Y | 任务ID |
| `associated_affair_id` | varchar(255) |  | Y | 关联事务Id |
| `specialty` | varchar(255) |  | Y | 专业 |
| `area` | varchar(255) |  | Y | 区域 |
| `affair_name` | varchar(255) |  | Y | 事务名称 |
| `ticket_flag` | int |  | Y | 是否需要开票（0：是，1：否） |
| `task_name` | varchar(255) |  | Y | 任务名称 |
| `task_properties` | varchar(255) |  | Y | 任务属性 |
| `task_equipment_name` | varchar(255) |  | Y | 任务设备名称 |
| `task_equipment_code` | varchar(255) |  | Y | 任务设备识别码 |
| `equipment_level` | varchar(255) |  | Y | 所属主体设备层级(1,2,3,4) 一级：设备本体（如压力容器） 二级：设备附件（如容器接管） 三级：附件配件（如接管阀门） 四级：配件零件（如阀门手轮） |
| `body_equipment_name` | varchar(255) |  | Y | 本体设备名称 |
| `body_equipment_code` | varchar(255) |  | Y | 主体设备编码 |
| `technical_id_code` | varchar(255) |  | Y | 主体设备位号 |
| `operation_department` | varchar(255) |  | Y | 运行部 |
| `execution_role` | varchar(255) |  | Y | 执行角色 |
| `zz_name` | varchar(255) |  | Y | 装置名称 |
| `project_leader` | varchar(255) |  | Y | 项目负责人（默认设备经理） |
| `job_type` | varchar(255) |  | Y | 作业类型 |
| `maintenance_type` | varchar(255) |  | Y | 检修类别() |
| `defect_phenomenon` | varchar(255) |  | Y | 缺陷现象 |
| `impact` | varchar(255) |  | Y | 影响 |
| `project_description` | varchar(4000) |  | Y | 项目描述 |
| `construction_specialty` | varchar(255) |  | Y | 项目专业 |
| `upload_auto` | varchar(255) |  | Y | 是否手动上传 |
| `report_user` | varchar(255) |  | Y | 提报人 |
| `report_time` | datetime |  | Y | 任务添加时间 |
| `file_name` | varchar(255) |  | Y | 文件名 |
| `file_path` | varchar(255) |  | Y | 文件路径 |
| `affair_type` | varchar(255) |  | Y | 事务类型 |
| `execution_type` | varchar(255) |  | Y | 执行形式（线上执行，自动生成；线下执行，上传表单；线下执行，执行确认，无需上传表单） |
| `template_path` | varchar(255) |  | Y | 模版路径 |
| `template_name` | varchar(255) |  | Y | 模板名  |
| `trigger_time` | varchar(255) |  | Y |  |
| `executions_required` | int |  | Y |  |
| `job_content` | varchar(1255) |  | Y |  |
| `executions_required_month` | int |  | Y |  |
| `frequency` | varchar(255) |  | Y | 中韩频次 |
| `new_trigger_time` | varchar(255) |  | Y | 统计最新的触发时间 |
| `module` | varchar(255) |  | Y | 模块 |
| `last_trigger_time` | varchar(255) |  | Y | 上次触发时间 |

**列实际取值（来自当前数据，LLM 选 WHERE 字面量时务必从这里挑）：**
- `specialty`：`仪` / `其他` / `动` / `电` / `综合` / `静`
- `area`：`乙烯` / `全厂` / `炼油`
- `equipment_level`：`/` / `一级` / `一级：设备本体（如压力容器）` / `三级` / `三级：附件配件（如接管阀门）` / `二级` / `二级：设备附件（如容器接管）`
- `operation_department`：`储运部` / `公用工程部` / `公用工程部(资产)` / `动力部` / `化工公用工程部` / `天津联维` / `检安公司` / `检验计量中心` / `炼油一部` / `炼油三部` / `炼油二部` / `炼油公用工程部` / `炼油四部` / `烯烃部` / `环氧芳烃部` / `维保单位` / `聚烯烃一部` / `聚烯烃二部` / `茂化建` / `设备工程部` …（共 22 个）
- `project_leader`：`定时性事务` / `设备经理`
- `job_type`：`日常检修`
- `maintenance_type`：`日常维护（M3)` / `日常维护（M3）` / `检修维修（M1或M2）`
- `defect_phenomenon`：`XX06预防性维护-X602施工配合` / `XX06预防性维护-X602施工配合-X602施工配合` / `XX06预防性维护-X602施工配合-undefined` / `XX06预防性维护-X602配合施工` / `null-undefined` / `null-undefined-undefined` / `null-undefined-undefined-undefined` / `null-undefined-undefined-undefined-undefined` / `null-undefined-undefined-undefined-undefined-undefined` / `undefined-undefined` / `undefined-undefined-undefined` / `undefined-undefined-undefined-undefined` / `undefined-undefined-undefined-undefined-undefined` / `undefined-undefined-undefined-undefined-undefined-undefined` / `undefined-undefined-undefined-undefined-undefined-undefined-undefined` / `undefined-undefined-undefined-undefined-undefined-undefined-undefined-undefined`
- `impact`：`无影响`
- `project_description`：` 6~35kV开关柜及其母线桥带电局放检测` / `110kV、220kVGIS带电局放检测` / `110kV或120MVA及以上变压器油色谱` / `35kVGIS带电局放检测` / `6~35kV开关柜及其母线桥开关柜及母线带电局放检测` / `SF6气体成分和水分检测` / `变压器数量和容量的N-1要求` / `固定式可燃及有毒气体报警器通气试验` / `对35kV及以上电力变压器电流检测` / `对35kV及以上电力变压器进行电流检测` / `对地下井仪表进水情况进行检查` / `对带部分行程测试功能的开关阀，应进行微动试验；对工艺具备试验条件的切断阀，应进行开关动作试验。` / `对易积灰、结焦、堵塞的传感器进行下线清理或在线手动强制反吹` / `对机柜间及在线分析小屋空调过滤网、室外机散热片进行清扫` / `对氧化锆分析仪的零点和量程进行标定。` / `检查6-35kV变压器各项运行参数及附件` / `每季度一次对贸易交接、能源及物料计量用质量流量计的基础零点、驱动增益、检测线圈电压、振动频率等运行状态参数进行检查` / `油系统蓄能器检查` / `炼油厂区 110kVGIS带电局放检测` / `蓄电池充放电` …（共 24 个）
- `construction_specialty`：`仪` / `动` / `电`
- `upload_auto`：`否` / `是`
- `report_user`：`付笙泰` / `刘嵩` / `周锦巧` / `李奇峰` / `沈忱` / `王惟一` / `王聪` / `袁民拥` / `邓强华` / `金坦`
- `file_name`：`/` / `光学仪表镜片清理记录` / `切断阀内漏试验记录` / `定位器I/P单元清扫记录` / `定期润滑记录` / `开关阀微动试验` / `执行机构内窥镜检测记录` / `接地连接电阻检测记录` / `接线箱检查记录` / `易积灰、结焦、堵塞的传感器清扫记录` / `柔性热电偶检查记录` / `液晶屏按键试验记录` / `环保监测仪表维护记录` / `联锁切断阀动作试验记录` / `通气试验记录` / `防腐蚀检测记录`
- `affair_type`：`会议总结类` / `执行确认类` / `检查巡检类` / `维护活动类`
- `execution_type`：`线上执行，自动生成表单` / `线下执行，上传表单` / `线下执行，执行确认，无需上传表单`
- `frequency`：`1次/2年` / `1次/两年` / `1次/半年` / `1次/周` / `1次/四年` / `1次/季度` / `1次/年` / `1次/日` / `1次/月` / `1次/月

` / `1次/检修周期` / `2次/月` / `三定周期` / `出厂超1年` / `及时` / `大修时` / `按法律规范、规程规定` / `按预防性维修计划执行`
- `last_trigger_time`：`2025-12-10 10:44:50` / `2025-12-10 10:44:53` / `2025-12-25 14:23:25` / `2025-12-25 14:23:35` / `2025-12-25 14:35:55` / `2025-12-25 14:36:08` / `2025-12-25 14:40:28` / `2025-12-25 14:40:38` / `2025-12-26 14:52:38` / `2025-12-26 14:52:48` / `2026-01-14 17:12:33` / `2026-01-14 17:26:36` / `2026-01-14 17:26:58`

### 表 `affair_task_pushed`

| 字段 | 类型 | 主键 | 可空 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | int | ✓ | N |  |
| `task_pushed_id` | varchar(255) |  | Y | 触发任务ID(唯一性) |
| `task_id` | varchar(255) |  | Y | 任务ID |
| `associated_affair_id` | varchar(255) |  | Y | 关联事务Id |
| `specialty` | varchar(255) |  | Y | 专业 |
| `area` | varchar(255) |  | Y | 区域 |
| `affair_name` | varchar(255) |  | Y | 事务名称 |
| `ticket_flag` | int |  | Y | 是否需要开票（0：是，1：否） |
| `task_name` | varchar(255) |  | Y | 任务名称 |
| `task_properties` | varchar(255) |  | Y | 任务属性 |
| `task_equipment_name` | varchar(255) |  | Y | 任务设备名称 |
| `task_equipment_code` | varchar(255) |  | Y | 任务设备识别码 |
| `equipment_level` | varchar(255) |  | Y | 所属主体设备层级(1,2,3,4) 一级：设备本体（如压力容器） 二级：设备附件（如容器接管） 三级：附件配件（如接管阀门） 四级：配件零件（如阀门手轮） |
| `body_equipment_name` | varchar(255) |  | Y | 本体设备名称 |
| `body_equipment_code` | varchar(255) |  | Y | 主体设备编码 |
| `technical_id_code` | varchar(255) |  | Y | 主体设备位号 |
| `operation_department` | varchar(255) |  | Y | 运行部 |
| `zz_name` | varchar(255) |  | Y | 装置名称 |
| `project_leader` | varchar(255) |  | Y | 项目负责人（默认设备经理） |
| `job_type` | varchar(255) |  | Y | 作业类型 |
| `maintenance_type` | varchar(255) |  | Y | 检修类别() |
| `defect_phenomenon` | varchar(255) |  | Y | 缺陷现象 |
| `impact` | varchar(255) |  | Y | 影响 |
| `project_description` | varchar(4000) |  | Y | 项目描述 |
| `construction_specialty` | varchar(255) |  | Y | 项目专业 |
| `upload_auto` | varchar(255) |  | Y | 是否手动上传 |
| `file_name` | varchar(255) |  | Y | 文件名 |
| `file_path` | varchar(255) |  | Y | 文件路径 |
| `task_state` | int |  | Y | 任务状态（0：待处理，1：已执行，2：已通过，3：未通过 ） |
| `deal_time` | datetime |  | Y | 提交时间 |
| `deal_user` | varchar(255) |  | Y | 执行人 |
| `associated_project_id` | varchar(255) |  | Y | 关联项目id |
| `defect_id` | varchar(255) |  | Y | 关联缺陷id |
| `delay_state` | int |  | Y | 延期状态（0：未申请，1：已申请，        2：延期申请通过，3：延期申请未通过） |
| `trigger_time` | datetime |  | Y | 触发时间 |
| `deadline` | datetime |  | Y | 截止时间 |
| `delay_time` | datetime |  | Y | 延期时间 |
| `approve_time` | datetime |  | Y | 审批时间 |
| `approver` | varchar(255) |  | Y | 审批人 |
| `execution_type` | varchar(255) |  | Y | 执行形式（线上执行，自动生成；线下执行，上传表单；线下执行，执行确认，无需上传表单） |
| `affair_type` | varchar(255) |  | Y | 事务类型 |
| `delay_reason` | varchar(255) |  | Y | 超期原因 |
| `template_name` | varchar(255) |  | Y | 模板名  |
| `template_path` | varchar(255) |  | Y | 模版路径 |
| `triggered` | int |  | Y | 已触发 |
| `completed` | int |  | Y | 已完成 |
| `executions_required` | int |  | Y | 应执行数 |
| `execution_role` | varchar(255) |  | Y | 执行角色 |

**列实际取值（来自当前数据，LLM 选 WHERE 字面量时务必从这里挑）：**
- `specialty`：`仪` / `其他` / `动` / `电` / `综合` / `静`
- `area`：`乙烯` / `全厂` / `化工` / `炼油`
- `equipment_level`：`/` / `一级` / `一级：设备本体（如压力容器）` / `三级` / `三级：附件配件（如接管阀门）` / `二级` / `二级：设备附件（如容器接管）`
- `operation_department`：`储运部` / `动力部` / `化工公用工程部` / `天津联维` / `检安公司` / `检验计量中心` / `炼油一部` / `炼油三部` / `炼油二部` / `炼油公用工程部` / `炼油四部` / `烯烃部` / `环氧芳烃部` / `维保单位` / `聚烯烃一部` / `聚烯烃二部` / `茂化建` / `设备工程部` / `设备工程部/设备运维技术中心` / `设备运维技术中心` …（共 23 个）
- `project_leader`：`定时性事务` / `设备经理`
- `job_type`：`日常检修`
- `maintenance_type`：`日常维护（M3)` / `日常维护（M3）` / `检修维修（M1或M2）`
- `defect_phenomenon`：`XX06预防性维护-X602施工配合` / `XX06预防性维护-X602施工配合-undefined` / `XX06预防性维护-X602配合施工` / `null-undefined` / `null-undefined-undefined` / `null-undefined-undefined-undefined` / `null-undefined-undefined-undefined-undefined` / `null-undefined-undefined-undefined-undefined-undefined` / `undefined-undefined` / `undefined-undefined-undefined` / `undefined-undefined-undefined-undefined` / `undefined-undefined-undefined-undefined-undefined` / `undefined-undefined-undefined-undefined-undefined-undefined` / `undefined-undefined-undefined-undefined-undefined-undefined-undefined` / `undefined-undefined-undefined-undefined-undefined-undefined-undefined-undefined`
- `impact`：`无影响`
- `project_description`：`110kV、220kVGIS带电局放检测` / `110kV或120MVA及以上变压器油色谱` / `SF6气体成分和水分检测` / `变压器数量和容量的N-1要求` / `对35kV及以上电力变压器电流检测` / `对35kV及以上电力变压器进行电流检测` / `对地下井仪表进水情况进行检查` / `对机柜间及在线分析小屋空调过滤网、室外机散热片进行清扫` / `对氧化锆分析仪的零点和量程进行标定。` / `检查6-35kV变压器各项运行参数及附件` / `每季度一次对贸易交接、能源及物料计量用质量流量计的基础零点、驱动增益、检测线圈电压、振动频率等运行状态参数进行检查` / `油系统蓄能器检查` / `炼油厂区 110kVGIS带电局放检测` / `蓄电池充放电` / `蓄电池内阻检测` / `防雷防静电检测：爆炸危险场所的防雷设施`
- `construction_specialty`：`仪` / `动` / `电`
- `upload_auto`：`否` / `是`
- `approver`：`朱圣威`
- `execution_type`：`线上执行，自动生成表单` / `线下执行，上传表单` / `线下执行，执行确认，上传表单` / `线下执行，执行确认，无需上传表单`
- `affair_type`：`会议总结类` / `执行确认类` / `检查巡检类` / `生产活动类` / `维护活动类`

### 表 `based_info`

| 字段 | 类型 | 主键 | 可空 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | int | ✓ | N | 自增id |
| `ea_id` | varchar(255) |  | Y | 运行部Id |
| `ea_name` | varchar(255) |  | Y | 运行部名，装置名 |
| `ea_title` | varchar(255) |  | Y | 分类 |
| `ea_code` | varchar(255) |  | Y | 代码，设备编码 |
| `ea_parent_ea_code` | varchar(255) |  | Y | 父级代码 |

**列实际取值（来自当前数据，LLM 选 WHERE 字面量时务必从这里挑）：**
- `ea_title`：`乙烯运行部` / `功能位置` / `工厂区域` / `维保单位` / `装置` / `运行部`

### 表 `check_form`

| 字段 | 类型 | 主键 | 可空 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | bigint | ✓ | N |  |
| `specialty` | varchar(255) |  | Y | 专业 |
| `affair_name` | varchar(255) |  | Y | 事务名称 |
| `task_name` | varchar(255) |  | Y | 任务名称 |
| `task_properties` | varchar(255) |  | Y | 任务属性 |
| `task_point_name` | varchar(255) |  | Y | 任务点名称 |
| `associated_equipment` | varchar(255) |  | Y | 关联设备 |
| `technical_id_code` | varchar(255) |  | Y | 关联设备位号 |
| `equipment_code` | varchar(255) |  | Y | 关联设备编码 |
| `check_name` | varchar(255) |  | Y | 检查项名称 |
| `check_require` | varchar(255) |  | Y | 检查要求 |
| `low_limit` | varchar(255) |  | Y | 低限值 |
| `high_limit` | varchar(255) |  | Y | 高限值 |
| `take_photo` | int |  | Y | 是否必须拍照记录（0是，1否） |
| `note` | varchar(255) |  | Y | 备注 |
| `check_id` | int |  | Y | 检查项id |
| `check_type` | int |  | Y | 检查项类型 |
| `options` | varchar(255) |  | Y | 选项（检查结果） |
| `check_content` | varchar(255) |  | Y | 检查项内容 |
| `file_name` | varchar(255) |  | Y |  |
| `file_path` | varchar(255) |  | Y |  |
| `remark` | varchar(255) |  | Y |  |
| `task_pushed_id` | varchar(255) |  | Y |  |

**列实际取值（来自当前数据，LLM 选 WHERE 字面量时务必从这里挑）：**
- `specialty`：`仪` / `动` / `电` / `静`
- `affair_name`：`A类UPS点巡检` / `A级控制阀巡回检查` / `分析仪表全覆盖巡回检查` / `加热炉月度检查` / `压力容器月度检查巡检` / `压力管道月度检查巡检` / `常压储罐月度检查` / `控制系统全覆盖巡回检查` / `控制阀专项巡回检查` / `机柜室巡检` / `油系统蓄能器检查` / `环保监测仪表维护` / `蒸汽透平速关阀检查`
- `low_limit`：`/` / `0.02` / `18` / `40`
- `high_limit`：`-20` / `/` / `0.04` / `28` / `60`
- `note`：`填写“异常”为异常状态` / `填写数值（18-28内正常，超出黄色报警提醒）` / `填写数值（40-60内正常，超出黄色报警提醒）` / `填写数值（不正常注明问题）` / `正常或不正常（默认填写正常，不正常直接填写问题）` / `正常或不正常（默认填写正常，不正常直接填写问题，至少拍摄一张机柜室整体照片表明到现场检查）` / `若选择停用或检修，提交后其他检查项自动带入停用或检修` / `若选择停用提交后，其他检查项自动带入停用；若选择无此项，则下次默认此项为灰，该表无此内容无需检查自动跳过该条。如检查结果为正常，备注为空；若检查结果异常，备注异常内容。` / `若选择停电，其他检查项自动填写“停电”。
若选择无，其他检查项自动填写“无”。
若选择备用，手动输入项自动填写“备用”。` / `若选择无，本条检查项结束。` / `若选择无，本条检查项结束。
待温湿度仪安装齐全后取消此项。`
- `options`：`主路供电/旁路供电/电池供电/检修旁路供电` / `是/否` / `有/无` / `正常/异常` / `正常/异常/停用/检修/无` / `运行/停用/检修`

### 表 `cron`

| 字段 | 类型 | 主键 | 可空 | 含义 |
| --- | --- | --- | --- | --- |
| `cron` | datetime |  | N | 定时时间，设定的作业超时时间 |
| `cron_flag` | int |  | N | 是否执行过定时任务，或定时任务已过期(0,1) |
| `task_id` | varchar(200) |  | N | 已触发任务id |
| `type` | varchar(255) |  | N | 类型 |

### 表 `defect`

| 字段 | 类型 | 主键 | 可空 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | int | ✓ | N | 自增id |
| `equipment_code` | varchar(255) |  | Y | 设备编码 |
| `task_pushed_id` | varchar(255) |  | Y |  |
| `operation_department` | varchar(255) |  | Y | 运行部 |
| `zz_name` | varchar(255) |  | Y | 装置名称 |
| `equipment_specialty` | varchar(255) |  | Y | 设备专业 |
| `equipment_description` | varchar(255) |  | Y | 设备描述 |
| `defect_phenomenon` | varchar(255) |  | Y | 缺陷现象 |
| `defect_phenomenon_concrete` | varchar(255) |  | Y | 缺陷现象具体 |
| `defect_state` | varchar(255) |  | Y | 缺陷状态 缺陷消除 自行整改 删除 待处理 临时处理完成 处理中 未处理 |
| `remarks` | varchar(255) |  | Y | 备注 |

### 表 `electrical_info`

| 字段 | 类型 | 主键 | 可空 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | int | ✓ | N | 自增id |
| `mark_code` | varchar(255) |  | Y | 识别码 |
| `equipment_code` | varchar(255) |  | Y | 设备编码 |
| `ark_code` | varchar(255) |  | Y | 柜编号 |
| `house_name` | varchar(255) |  | Y | 所属配电间 |
| `drawer_code` | varchar(255) |  | Y | 抽屉编号 |
| `loop_code` | varchar(255) |  | Y | 回路编号 |
| `loop_process_code` | varchar(255) |  | Y | 回路工艺编号 |
| `loop_name` | varchar(255) |  | Y | 回路名称 |
| `loop_type` | varchar(255) |  | Y | 回路类型 |
| `current_limit` | float(81,1) |  | Y | 电流限高 |
| `inspection_type` | varchar(255) |  | Y | 巡检类别 |
| `associated_ea_id` | varchar(255) |  | Y | 关联基础表中的ea_id |
| `frequency` | varchar(255) |  | Y | 频次 |

**列实际取值（来自当前数据，LLM 选 WHERE 字面量时务必从这里挑）：**
- `house_name`：`中压变频室` / `加氢裂化UPS室` / `加氢裂化开闭所` / `加氢裂化装置主控室UPS` / `加氢裂化装置加氢裂化机柜室UPS` / `加氢裂化配电间` / `励磁室` / `干气配电间` / `开闭所`
- `drawer_code`：`/` / `1` / `2` / `3` / `4` / `5` / `6` / `7` / `8` / `9` / `上`
- `loop_type`：`K4102A` / `K4103A` / `PT回路` / `母联回路` / `直流屏` / `进线回路` / `配出回路`
- `inspection_type`：`加氢裂化UPS室` / `加氢裂化励磁室` / `加氢裂化变频室` / `加氢裂化开闭所高压柜` / `加氢裂化配电间低压柜` / `结构型巡检`
- `associated_ea_id`：`装置_A01`
- `frequency`：`每天`

### 表 `electrical_time_task`

| 字段 | 类型 | 主键 | 可空 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | int | ✓ | N | 自增id |
| `time_task_id` | varchar(255) |  | Y | 定时性任务唯一id |
| `operation_department` | varchar(255) |  | Y | 运行部 |
| `zz_name` | varchar(255) |  | Y | 装置 |
| `equipment_specialty` | varchar(255) |  | Y | 设备专业 |
| `equipment_code` | varchar(255) |  | Y | 设备编码 |
| `mark_code` | varchar(255) |  | Y | 识别码 |
| `ark_code` | varchar(255) |  | Y | 柜编号 |
| `drawer_code` | varchar(255) |  | Y | 抽屉编号 |
| `loop_code` | varchar(255) |  | Y | 回路编号 |
| `loop_process_code` | varchar(255) |  | Y | 回路工艺编号 |
| `loop_name` | varchar(255) |  | Y | 回路名称 |
| `current_limit` | float(81,1) |  | Y | 电流限高 |
| `house_name` | varchar(255) |  | Y | 所属配电间 |
| `day_flag` | int |  | Y | 频率标准位（0：每天，1：每周） |
| `trigger_time` | datetime |  | Y | 触发时间 |
| `task_date` | varchar(255) |  | Y | 任务时间 |
| `task_state` | int |  | Y | 任务状态（0：待处理，1：完成，2：异常） |
| `deal_time` | datetime |  | Y | 处理时间 |
| `deal_user` | varchar(255) |  | Y | 处理人 |
| `loop_type` | varchar(255) |  | Y | 回路类型 |
| `inspection_type` | varchar(255) |  | Y | 巡检类别 |
| `file_name` | varchar(500) |  | Y | 文件名 |
| `file_path` | varchar(500) |  | Y | 文件路径 |

**列实际取值（来自当前数据，LLM 选 WHERE 字面量时务必从这里挑）：**
- `operation_department`：`炼油三部`
- `zz_name`：`加氢裂化`
- `equipment_specialty`：`电`
- `drawer_code`：`/` / `1` / `2` / `3` / `4` / `5` / `6` / `7` / `8` / `9` / `上`
- `house_name`：`46` / `中压变频室` / `加氢裂化UPS室` / `加氢裂化开闭所` / `加氢裂化装置主控室UPS` / `加氢裂化装置加氢裂化机柜室UPS` / `加氢裂化配电间` / `励磁室` / `干气配电间` / `开闭所`
- `task_date`：`20221123` / `20221125` / `20221126` / `20221127` / `20221128` / `20221129` / `20221130` / `20221201` / `20221203` / `20221205` / `20221206` / `20221207` / `202249` / `20230320` / `20230324`
- `deal_user`：`刘嵩`
- `loop_type`：`K4102A` / `K4103A` / `PT回路` / `母联回路` / `直流屏` / `进线回路` / `配出回路`
- `inspection_type`：`55` / `加氢裂化UPS室` / `加氢裂化励磁室` / `加氢裂化变频室` / `加氢裂化开闭所高压柜` / `加氢裂化配电间低压柜` / `结构型巡检`
- `file_name`：`221130192549EXJ221126153054.pdf` / `221130194059EXJ221126153054.pdf` / `EXJ221130151654.pdf` / `EXJ221201104108.pdf` / `EXJ221201104152.pdf` / `EXJ221206101509.pdf` / `EXJ221206101516.pdf` / `EXJ221206101772.pdf` / `EXJ221206101775.pdf` / `EXJ221206101792.pdf` / `EXJ221206101825.pdf` / `EXJ221206101856.pdf` / `EXJ221206101862.pdf` / `EXJ221207104951.pdf` / `EXJ221207104952.pdf` / `EXJ221207104966.pdf` / `EXJ230320162248.pdf`
- `file_path`：`20221130/221130192549EXJ221126153054.pdf` / `20221130/221130194059EXJ221126153054.pdf` / `20221130/EXJ221130151654.pdf` / `20221201/EXJ221201104108.pdf` / `20221201/EXJ221201104152.pdf` / `20221206/EXJ221206101509.pdf` / `20221206/EXJ221206101516.pdf` / `20221206/EXJ221206101772.pdf` / `20221206/EXJ221206101775.pdf` / `20221206/EXJ221206101792.pdf` / `20221206/EXJ221206101825.pdf` / `20221206/EXJ221206101856.pdf` / `20221206/EXJ221206101862.pdf` / `20221207/EXJ221207104951.pdf` / `20221207/EXJ221207104952.pdf` / `20221207/EXJ221207104966.pdf` / `20230320/EXJ230320162248.pdf`

### 表 `electrical_time_task_submit`

| 字段 | 类型 | 主键 | 可空 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | int | ✓ | N | 自增id |
| `time_task_id` | varchar(255) |  | Y | 定时性任务唯一id |
| `total_state` | int |  | Y | 整体异常状态（2：异常，1：正常） |
| `state` | varchar(255) |  | Y | 检查项异常状态 |
| `reason` | text |  | Y | 检查项异常理由 |
| `num` | text |  | Y | 检查项填写数据 |
| `battery_state` | varchar(255) |  | Y | 开闭所蓄电池充电状态检查 |
| `excitation_module` | varchar(255) |  | Y | 励磁室励磁运行模式 |
| `control_module` | varchar(255) |  | Y | 励磁室控制模块运行模式 |
| `power_module` | varchar(255) |  | Y | UPS供电模式 |
| `electrical_note` | varchar(255) |  | Y | 备注 |
| `electrical_image` | varchar(255) |  | Y | 电气检查图片 |

**列实际取值（来自当前数据，LLM 选 WHERE 字面量时务必从这里挑）：**
- `time_task_id`：`EXJ221129103011` / `EXJ221130151654` / `EXJ221201104108` / `EXJ221201104152` / `EXJ221203134609` / `EXJ221203134823` / `EXJ221205092923` / `EXJ221205093033` / `EXJ221206101509` / `EXJ221206101516` / `EXJ221206101517` / `EXJ221206101518` / `EXJ221206101519` / `EXJ221206101520` / `EXJ221206101772` / `EXJ221206101773` / `EXJ221206101775` / `EXJ221206101776` / `EXJ221206101792` / `EXJ221206101825` …（共 28 个）
- `state`：`异常;正常;正常;异常` / `异常;正常;正常;正常` / `正常;异常;正常;异常;正常` / `正常;异常;正常;正常` / `正常;正常;异常;正常` / `正常;正常;异常;正常;正常;正常;正常` / `正常;正常;正常;` / `正常;正常;正常;异常` / `正常;正常;正常;正常` / `正常;正常;正常;正常;异常` / `正常;正常;正常;正常;异常;正常;正常` / `正常;浮充;正常`
- `battery_state`：`正常`
- `electrical_note`：`11` / `111` / `1111` / `124` / `13` / `2` / `22` / `222` / `2222` / `22222` / `33` / `4444` / `555` / `888`
- `electrical_image`：`20221203/EXJ2212031346090.jpg` / `20221206/EXJ2212061015210.jpg<>20221206/EXJ2212061015210.jpg` / `20221206/EXJ2212061017740.jpg` / `20221206/EXJ2212061017761.jpg`

### 表 `equip_archi`

| 字段 | 类型 | 主键 | 可空 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | int | ✓ | N | 自增id |
| `ea_id` | varchar(255) |  | Y | 运行部Id |
| `ea_name` | varchar(255) |  | Y | 运行部名，装置名 |
| `ea_title` | varchar(255) |  | Y | 分类 |
| `ea_code` | varchar(255) |  | Y | 代码 |
| `ea_parent_ea_code` | varchar(255) |  | Y | 父级代码 |

**列实际取值（来自当前数据，LLM 选 WHERE 字面量时务必从这里挑）：**
- `ea_title`：`乙烯运行部` / `功能位置` / `工厂区域` / `装置` / `运行部`

### 表 `equip_archi_backup`

| 字段 | 类型 | 主键 | 可空 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | int | ✓ | N | 自增id |
| `ea_id` | varchar(255) |  | Y | 运行部Id |
| `ea_name` | varchar(255) |  | Y | 运行部名，装置名 |
| `ea_title` | varchar(255) |  | Y | 分类 |
| `ea_code` | varchar(255) |  | Y | 代码 |
| `ea_parent_ea_code` | varchar(255) |  | Y | 父级代码 |

**列实际取值（来自当前数据，LLM 选 WHERE 字面量时务必从这里挑）：**
- `ea_title`：`乙烯运行部` / `功能位置` / `工厂区域` / `装置` / `运行部`

### 表 `equiparchi_to_user`

| 字段 | 类型 | 主键 | 可空 | 含义 |
| --- | --- | --- | --- | --- |
| `ea_id` | varchar(255) |  | Y |  |
| `user_zhsh` | varchar(255) |  | Y |  |

**列实际取值（来自当前数据，LLM 选 WHERE 字面量时务必从这里挑）：**
- `ea_id`：`乙烯运行部_W01` / `乙烯运行部_W02` / `乙烯运行部_W03` / `乙烯运行部_W04` / `乙烯运行部_W05` / `乙烯运行部_W06` / `乙烯运行部_W07` / `乙烯运行部_W10` / `化工公用工程部` / `厂部` / `检安公司公司` / `运行部` / `运行部_A01` / `运行部_A02` / `运行部_A03` / `运行部_A04` / `运行部_A05` / `运行部_A06` / `运行部_A07` / `运行部_A08` …（共 30 个）

### 表 `equipment_info`
> 设备信息表（仅核心字段非空）

| 字段 | 类型 | 主键 | 可空 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | int | ✓ | N | 自增主键（序号） |
| `area` | varchar(50) |  | N | 区域（非空） |
| `operation_department` | varchar(50) |  | Y | 运行部（允许为空） |
| `equipment_code` | varchar(20) |  | N | 设备编号（非空） |
| `equipment_name` | varchar(100) |  | N | 设备名称（非空） |
| `module_partition` | varchar(20) |  | Y | 模块分区（允许为空） |
| `zz_name` | varchar(50) |  | N | 安装位置（非空） |
| `technical_id_code` | varchar(50) |  | N | 位号（非空） |
| `product_grade` | varchar(20) |  | Y | 品等（允许为空） |
| `license_number` | varchar(50) |  | Y | 使用证编号（允许为空） |
| `2024_inspection_org` | varchar(100) |  | Y | 2024年大修检验机构（允许为空） |
| `safety_status` | varchar(10) |  | Y | 安全状态等级（允许为空） |
| `safety_condition` | varchar(10) |  | Y | 安全状况等级 |
| `put_into_use_date` | varchar(50) |  | Y | 投用日期（允许为空，格式：YYYY-MM-DD） |
| `registration_code` | varchar(30) |  | Y | 设备注册代码（允许为空） |
| `next_inspection_date` | varchar(50) |  | Y | 下次检验日期（允许为空，格式：YYYY-MM-DD） |
| `report_number` | varchar(50) |  | Y | 报告编号（允许为空） |
| `created_at` | timestamp |  | Y | 记录创建时间 |
| `updated_at` | timestamp |  | Y | 记录更新时间 |

**列实际取值（来自当前数据，LLM 选 WHERE 字面量时务必从这里挑）：**
- `area`：`炼油`
- `operation_department`：`储运部` / `公用工程部` / `公用工程部(资产)` / `检验计量中心` / `炼油一部` / `炼油三部` / `炼油二部` / `炼油四部`
- `module_partition`：`A` / `B` / `C` / `D` / `E` / `F` / `G` / `H`
- `product_grade`：`2` / `Ⅰ` / `Ⅱ` / `Ⅲ`
- `2024_inspection_org`：`中国特种设备检测研究院` / `中石化工程质量监测有限公司` / `制造监检` / `华中` / `华中站` / `湖北特种设备检验检测研究院` / `湖南百思检验检测有限公司`
- `safety_status`：`0` / `1` / `1#催化` / `1#制氢不检` / `2` / `2级` / `3` / `3级` / `5` / `不检` / `制氢` / `报告不对` / `更新`
- `safety_condition`：`0` / `1` / `2` / `3`

### 表 `form_submit`

| 字段 | 类型 | 主键 | 可空 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | int |  | Y |  |
| `check_content` | varchar(255) |  | Y | 填写内容或选择项 |
| `file_name` | varchar(255) |  | Y |  |
| `file_path` | varchar(255) |  | Y |  |
| `remark` | varchar(255) |  | Y | 备注 |
| `check_id` | varchar(255) |  | Y | 检查项id |
| `task_pushed_id` | varchar(255) |  | Y | 任务唯一性id |
| `task_properties` | varchar(255) |  | Y | 任务属性 |
| `time` | datetime |  | Y |  |
| `abnormal` | int |  | Y | 数据是否异常（1为异常，null正常） |

**列实际取值（来自当前数据，LLM 选 WHERE 字面量时务必从这里挑）：**
- `task_properties`：`A类UPS点巡检` / `A级控制阀巡回检查` / `常压储罐月度检查` / `循环压缩机` / `循环氢压缩机K6102油系统蓄能器检查` / `控制系统全覆盖巡回检查` / `油系统蓄能器检查` / `炼油加热炉月度检查` / `蒸汽透平速关阀检查` / `重整1#UPS点巡检` / `重整15#UPS点巡检` / `重整蒸发塔底重沸炉F103检查`

### 表 `instrument_info`

| 字段 | 类型 | 主键 | 可空 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | int | ✓ | N | 自增id |
| `equipment_code` | varchar(255) |  | Y | 设备编码 |
| `mark_code` | varchar(255) |  | Y | 识别码 |
| `cabinet_name` | varchar(255) |  | Y | 机柜名称 |
| `cabinet_class` | varchar(255) |  | Y | 机柜类别 |
| `house_name` | varchar(255) |  | Y | 现场区域 |
| `associated_ea_id` | varchar(255) |  | Y | 关联基础表中的ea_id |
| `frequency` | varchar(255) |  | Y | 频次 |

**列实际取值（来自当前数据，LLM 选 WHERE 字面量时务必从这里挑）：**
- `cabinet_class`：`仪表3500系统` / `仪表CCS系统` / `仪表DCS系统` / `仪表SIS系统` / `仪表外配柜` / `仪表控制系统环境` / `仪表无极气量调节系统` / `仪表机柜室环境` / `仪表电源柜` / `仪表系统柜`
- `house_name`：`加氢裂化仪表机柜室` / `加氢裂化控制系统`
- `associated_ea_id`：`装置_A01` / `装置_A02` / `装置_A03`
- `frequency`：`每周` / `每天`

### 表 `instrument_time_task`

| 字段 | 类型 | 主键 | 可空 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | int | ✓ | N | 自增id |
| `time_task_id` | varchar(255) |  | Y | 定时性任务唯一id |
| `operation_department` | varchar(255) |  | Y | 运行部 |
| `zz_name` | varchar(255) |  | Y | 装置 |
| `equipment_specialty` | varchar(255) |  | Y | 设备专业 |
| `equipment_code` | varchar(255) |  | Y | 设备编码 |
| `mark_code` | varchar(255) |  | Y | 识别码 |
| `house_name` | varchar(255) |  | Y | 所属配电间 |
| `cabinet_name` | varchar(255) |  | Y | 机柜名称 |
| `cabinet_class` | varchar(255) |  | Y | 机柜类别 |
| `day_flag` | int |  | Y | 频率标准位（0：每天，1：每周） |
| `trigger_time` | datetime |  | Y | 触发时间 |
| `task_date` | varchar(255) |  | Y | 任务时间 |
| `task_state` | int |  | Y | 任务状态（0：待处理，1：完成，2：异常） |
| `deal_time` | datetime |  | Y | 处理时间 |
| `deal_user` | varchar(255) |  | Y | 处理人 |
| `inspection_type` | varchar(255) |  | Y | 巡检类别 |
| `file_name` | varchar(500) |  | Y | 文件名 |
| `file_path` | varchar(500) |  | Y | 文件路径 |

**列实际取值（来自当前数据，LLM 选 WHERE 字面量时务必从这里挑）：**
- `operation_department`：`炼油三部`
- `zz_name`：`2#制氢` / `加氢裂化` / `干气提浓`
- `equipment_specialty`：`仪`
- `house_name`：`加氢裂化仪表机柜室` / `加氢裂化控制系统`
- `cabinet_class`：`仪表3500系统` / `仪表CCS系统` / `仪表DCS系统` / `仪表SIS系统` / `仪表外配柜` / `仪表控制系统环境` / `仪表无极气量调节系统` / `仪表机柜室环境` / `仪表电源柜` / `仪表系统柜`
- `task_date`：`20221201` / `20221203` / `20221205` / `20221206` / `20221207` / `202249` / `202250` / `20230320` / `20230324` / `202312`
- `deal_user`：`刘嵩`
- `file_name`：`IXJ221201160008.pdf` / `IXJ221201160009.pdf` / `IXJ221201160010.pdf` / `IXJ221201160011.pdf` / `IXJ221201160012.pdf` / `IXJ221201160013.pdf` / `IXJ221203134536.pdf` / `IXJ221203134537.pdf` / `IXJ221203134541.pdf` / `IXJ221206101467.pdf` / `IXJ221206101468.pdf` / `IXJ221206101469.pdf` / `IXJ221206101470.pdf` / `IXJ221206101471.pdf` / `IXJ221206101491.pdf` / `IXJ221206101500.pdf` / `IXJ221206101501.pdf` / `IXJ221206215717.pdf` / `IXJ221206215721.pdf`
- `file_path`：`20221203/IXJ221201160008.pdf` / `20221203/IXJ221201160009.pdf` / `20221203/IXJ221201160010.pdf` / `20221203/IXJ221201160011.pdf` / `20221203/IXJ221201160012.pdf` / `20221203/IXJ221201160013.pdf` / `20221203/IXJ221203134536.pdf` / `20221203/IXJ221203134537.pdf` / `20221203/IXJ221203134541.pdf` / `20221206/IXJ221206101467.pdf` / `20221206/IXJ221206101468.pdf` / `20221206/IXJ221206101469.pdf` / `20221206/IXJ221206101470.pdf` / `20221206/IXJ221206101471.pdf` / `20221207/IXJ221206101491.pdf` / `20221207/IXJ221206101500.pdf` / `20221207/IXJ221206101501.pdf` / `20221207/IXJ221206215717.pdf` / `20221207/IXJ221206215721.pdf`

### 表 `instrument_time_task_submit`

| 字段 | 类型 | 主键 | 可空 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | int | ✓ | N | 自增id |
| `time_task_id` | varchar(255) |  | Y | 定时性任务唯一id |
| `total_state` | int |  | Y | 整体异常状态（2：异常，1：正常） |
| `state` | varchar(255) |  | Y | 检查项异常状态 |
| `reason` | text |  | Y | 检查项异常理由 |
| `num` | text |  | Y | 检查项填写数据 |
| `instrument_image` | varchar(255) |  | Y | 仪表检查图片 |
| `instrument_note` | varchar(255) |  | Y | 备注 |

**列实际取值（来自当前数据，LLM 选 WHERE 字面量时务必从这里挑）：**
- `time_task_id`：`IXJ221201160008` / `IXJ221206101463` / `IXJ221206101464` / `IXJ221206101465` / `IXJ221206101466` / `IXJ221206101467` / `IXJ221206101468` / `IXJ221206101469` / `IXJ221206101470` / `IXJ221206101471` / `IXJ221206101491` / `IXJ221206101500` / `IXJ221206101501` / `IXJ221206215717` / `IXJ221206215721`
- `state`：`异常` / `正常` / `正常;异常;正常;正常` / `正常;正常` / `正常;正常;异常;正常` / `正常;正常;正常;异常` / `正常;正常;正常;正常`
- `instrument_note`：`11` / `111` / `1111` / `111111222` / `123` / `222` / `2222`

### 表 `login_info`

| 字段 | 类型 | 主键 | 可空 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | int | ✓ | N | 自增主键 |
| `user_zhsh` | varchar(255) |  | Y | 账号唯一id，对应统一身份认证 |
| `user_name` | varchar(255) |  | Y | 用户名 |
| `time` | datetime |  | Y | 时间 |
| `state` | int |  | Y | 0：登入，1：登出 |
| `source` | varchar(255) |  | Y | 来源 |

**列实际取值（来自当前数据，LLM 选 WHERE 字面量时务必从这里挑）：**
- `source`：`Android` / `Mac` / `Unix` / `Windows`

### 表 `menus`

| 字段 | 类型 | 主键 | 可空 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | int | ✓ | N | 自增id |
| `menu_code` | int |  | N | 菜单id |
| `menu_name` | varchar(255) | ✓ | N | 菜单名 |
| `menu_component` | varchar(255) |  | N | 菜单内容 |
| `menu_path` | varchar(255) |  | N | 菜单路由 |
| `parent_id` | int |  | N | 与menu_code对应，一级菜单为-1，其他为父级菜单的menu_code |
| `menu_icon_path` | varchar(255) |  | Y | 菜单图标路径 |
| `menu_type` | varchar(255) |  | Y | 菜单类型 |
| `remark` | varchar(255) |  | Y | 备注 |
| `create_person` | varchar(255) |  | N | 创建人 |
| `create_time` | datetime |  | N | 创建时间 |
| `change_person` | varchar(255) |  | Y | 修改人 |
| `change_time` | datetime |  | Y | 修改时间 |
| `hidden` | varchar(255) |  | N | 是否隐藏 |

**列实际取值（来自当前数据，LLM 选 WHERE 字面量时务必从这里挑）：**
- `menu_name`：`年度统计总表` / `月度统计总表` / `运行部执行率统计表` / `下月事务统计` / `专业维度执行率统计表` / `主页` / `人员信息` / `人员管理` / `仪表定时巡检` / `定时事务` / `定时事务统计` / `定时巡检` / `定时性事务` / `已触发任务` / `新增事务` / `检查表单` / `电气定时巡检` / `统计报表` / `表单管理`
- `menu_component`：`Index` / `Layout` / `departmentAffairList` / `electricalTimingTask` / `formManagement` / `instrumentTimingTask` / `manualTask` / `peopleManagement` / `statisticsList`
- `menu_path`：`/formManagement/checkForms` / `/index` / `/inspection/electricalTimingTask` / `/inspection/instrumentTimingTask` / `/layout` / `/manualTask/addAffairReport` / `/manualTask/pendThing` / `/manualTask/timingAffairsComprehensive` / `/rightsManagement/peopleManagement` / `/statisticsList/annualAffairTable` / `/statisticsList/departmentAffairList` / `/statisticsList/departmentImplementationTable` / `/statisticsList/monthAffairTable` / `/statisticsList/nextTasksList` / `/statisticsList/specialtyImplementationTable`
- `menu_icon_path`：`el-icon-caret-right`
- `menu_type`：`first` / `second` / `secood`
- `remark`：`一级` / `二级`
- `create_person`：`admin`
- `change_person`：`admin`
- `hidden`：`false` / `true`

### 表 `report_results`
> 报告结果表

| 字段 | 类型 | 主键 | 可空 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | int | ✓ | N |  |
| `task_pushed_id` | varchar(255) |  | Y | 任务推送ID |
| `equipment_code` | varchar(255) |  | Y | 设备编码 |
| `body_equipment_name` | varchar(255) |  | Y | 主体设备名称 |
| `technical_id_code` | varchar(255) |  | Y | 设备位号 |
| `trigger_time` | varchar(255) |  | Y | 触发时间 |
| `operation_department` | varchar(255) |  | Y | 运行部 |
| `result` | varchar(255) |  | Y | 结果 |

### 表 `role`

| 字段 | 类型 | 主键 | 可空 | 含义 |
| --- | --- | --- | --- | --- |
| `role_id` | int | ✓ | N | 自增id |
| `role_name` | varchar(255) |  | Y | 系统角色 |
| `role_desc` | varchar(255) |  | Y | 角色说明 |

### 表 `special_task`
> 特护任务表

| 字段 | 类型 | 主键 | 可空 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | int | ✓ | N | 主键 |
| `task_id` | int |  | Y | 任务id |
| `associated_affair_id` | varchar(255) |  | Y | 关联事物id |
| `department_name` | varchar(255) |  | Y | 部门名称 |
| `device_name` | varchar(255) |  | Y | 设备名称 |
| `equipment_id` | varchar(255) |  | Y | 设备id |
| `equipment_desc` | varchar(255) |  | Y | 设备描述 |
| `specialty` | varchar(255) |  | Y | 专业 |
| `trigger_time` | datetime |  | Y | 触发时间 |
| `deadline` | datetime |  | Y | 截止时间 |
| `current_week_number` | int |  | Y | 当前周数 |
| `is_timeout` | int |  | Y | 0：未超时 1:已超时 |
| `execution_role` | varchar(255) |  | Y | 执行角色 |
| `task_type` | varchar(255) |  | Y | 日检 周检 特护 |
| `create_by` | varchar(255) |  | Y | 创建人 |
| `create_time` | datetime |  | Y | 创建时间 |
| `update_by` | datetime |  | Y | 更新人 |
| `update_time` | datetime |  | Y | 更新时间 |
| `del_flag` | varchar(255) |  | Y | 删除标志 |
| `remark` | varchar(255) |  | Y | 备注 |

**列实际取值（来自当前数据，LLM 选 WHERE 字面量时务必从这里挑）：**
- `department_name`：`动力部` / `炼油一部` / `炼油三部` / `炼油二部` / `炼油公用工程部` / `炼油四部` / `烯烃部` / `环氧芳烃部` / `聚烯烃一部` / `聚烯烃二部`
- `device_name`：`1#焦化-炼油` / `1#聚丙烯装置ST-化工` / `2#HDPE装置-化工` / `2#催化-炼油` / `2#柴油加氢-炼油` / `2#焦化-炼油` / `2#聚丙烯装置JPP-化工` / `3#催化-炼油` / `3#柴油加氢-炼油` / `3#聚丙烯装置-化工` / `EO/EG装置-化工` / `HDPE装置-化工` / `LLDPE装置-化工` / `乙烯装置-化工` / `余热发电-炼油` / `加氢裂化-炼油` / `反应进料泵P6102A` / `反应进料泵P6102B` / `干气提浓-炼油` / `热电联产装置-化工` …（共 23 个）
- `specialty`：`仪` / `操` / `机` / `电` / `管`
- `task_type`：`周检` / `日检` / `特护`

### 表 `special_unit_device_config`

| 字段 | 类型 | 主键 | 可空 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | int | ✓ | N | 主键 |
| `department_name` | varchar(255) |  | Y | 部门 |
| `device_name` | varchar(255) |  | Y | 装置名称 |
| `equipment_id` | varchar(255) |  | Y | 设备id |
| `equipment_desc` | varchar(255) |  | Y | 设备描述 |
| `check_specialty` | varchar(255) |  | Y | 专业 |
| `check_item` | varchar(255) |  | Y | 巡检项 |
| `sub_device_id` | varchar(255) |  | Y | 子设备id（用于提报缺陷） |
| `sub_device` | varchar(255) |  | Y | 子设备 |
| `check_standard` | text |  | Y | 检查标准 |
| `unit` | varchar(255) |  | Y | 单位 |
| `min_value` | float |  | Y | 最小值 |
| `max_value` | float |  | Y | 最大值 |
| `checkItem_type` | int |  | Y | 填写类型 0 输入 1选择 |
| `check_method` | varchar(255) |  | Y | 检查方法 |
| `is_report_defect` | int |  | Y | 是否提报缺陷 0：是 1：否 |
| `is_data_collect` | int |  | Y | 是否需要数据采集0: 需要 1：不需要 |
| `item_type` | varchar(255) |  | Y | 巡检类型  |
| `data_collect` | varchar(255) |  | Y | 数据采集标签 |
| `create_by` | varchar(0) |  | Y | 创建人 |
| `create_time` | datetime |  | Y | 创建时间 |
| `update_by` | varchar(255) |  | Y | 更新人 |
| `update_time` | datetime |  | Y | 更新时间 |
| `del_flag` | varchar(255) |  | Y | 删除标志 |
| `remark` | varchar(255) |  | Y | 备注 |

**列实际取值（来自当前数据，LLM 选 WHERE 字面量时务必从这里挑）：**
- `department_name`：`1` / `动力部` / `炼油一部` / `炼油三部` / `炼油二部` / `炼油公用工程部` / `炼油四部` / `烯烃部` / `环氧芳烃部` / `聚烯烃一部` / `聚烯烃二部` / `聚烯烃部` / `钢石气体`
- `device_name`：`1#焦化-炼油` / `1#聚丙烯装置ST-化工` / `2#HDPE装置-化工` / `2#催化-炼油` / `2#柴油加氢-炼油` / `2#焦化-炼油` / `2#聚丙烯装置JPP-化工` / `3#催化-炼油` / `3#柴油加氢-炼油` / `3#聚丙烯装置-化工` / `3#聚丙烯装置-化工化工` / `EO/EG装置-化工` / `HDPE装置-化工` / `LLDPE装置-化工` / `乙烯装置-化工` / `余热发电-炼油` / `加氢裂化-炼油` / `干气提浓-炼油` / `热电联产装置-化工` / `焦化汽油加氢-炼油` …（共 23 个）
- `check_specialty`：`仪` / `操` / `机` / `电` / `管`
- `sub_device_id`：`203283142` / `203384795` / `203384796` / `203384809` / `203384828` / `203384829` / `203605919` / `203605920` / `203605921` / `203605922` / `203605923` / `203605924` / `203606003` / `203606004` / `203606005` / `203606006` / `203606008` / `203606010` / `204015181` / `204015219` …（共 24 个）
- `unit`：`%` / `A` / `Kpa.A` / `MPa` / `MPa(绝)` / `MPaG` / `MW` / `Nm3` / `Nm3/h` / `Nm3/hr` / `bar` / `dBsv` / `kPa` / `kg/h` / `m3/H` / `mm` / `mm/s` / `mm/s2` / `r/min` / `rmp` …（共 29 个）
- `item_type`：`周检` / `日检`

### 表 `special_unit_device_record`

| 字段 | 类型 | 主键 | 可空 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | int |  | Y | 主键id |
| `task_id` | int |  | Y | 关联任务id |
| `equipment_id` | varchar(20) |  | Y | 设备id |
| `device_name` | varchar(255) |  | Y | 设备名称 |
| `check_specialty` | varchar(255) |  | Y | 检查专业 |
| `check_item` | varchar(255) |  | Y | 检查项目 |
| `sub_device` | varchar(255) |  | Y | 子设备 |
| `check_standard` | text |  | Y | 检查标准 |
| `check_method` | varchar(255) |  | Y | 检查方法  |
| `check_result` | varchar(255) |  | Y | 检查结果 |
| `inspector` | varchar(255) |  | Y | 点检人员 |
| `report_time` | date |  | Y | 触发时间 |
| `check_time` | datetime |  | Y | 检查时间  |
| `is_abnormal` | varchar(255) |  | Y | 是否异常 |
| `item_type` | varchar(255) |  | Y | 记录任务类型 |
| `is_timeout` | int |  | Y | 是否为最新记录（0：是，1：不是） |
| `deadline_time` | date |  | Y | 截止时间 |
| `current_week_number` | int |  | Y | 当前周数 |
| `create_by` | varchar(255) |  | Y | 创建人 |
| `create_time` | datetime |  | Y | 创建时间 |
| `update_by` | varchar(255) |  | Y | 更新人 |
| `update_time` | datetime |  | Y | 更新时间 |
| `del_flag` | varchar(255) |  | Y | 删除标志 |
| `remark` | varchar(255) |  | Y | 备注 |

**列实际取值（来自当前数据，LLM 选 WHERE 字面量时务必从这里挑）：**
- `equipment_id`：`203280046` / `203298592` / `203298619`
- `device_name`：`EO/EG装置-化工` / `热电联产装置-化工`
- `check_specialty`：`仪` / `操` / `机` / `电` / `管`
- `check_method`：`DEH数据` / `回油视镜` / `就地控制柜` / `测量` / `现场表` / `玻璃视镜` / `目视` / `视镜`
- `inspector`：`王聪`
- `is_abnormal`：`异常` / `正常`
- `item_type`：`周检` / `日检`

### 表 `special_unit_ledger`

| 字段 | 类型 | 主键 | 可空 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | varchar(64) | ✓ | N | 主键id |
| `department_name` | varchar(100) |  | N | 部门名称 |
| `area_name` | varchar(255) |  | Y | 区域 |
| `device_name` | varchar(255) |  | Y | 装置 名称 |
| `equipment_id` | varchar(20) |  | Y | 设备id |
| `equipment_desc` | varchar(255) |  | Y | 设备描述 |
| `status` | varchar(1) |  | Y | 状态（1启用 0禁用） |
| `create_by` | varchar(255) |  | Y | 创建人 |
| `create_time` | datetime |  | Y | 创建时间 |
| `update_by` | varchar(255) |  | Y | 更新人 |
| `update_time` | datetime |  | Y | 更新时间 |
| `del_flag` | varchar(10) |  | Y | 删除标志 |
| `remark` | text |  | Y | 备注 |

**列实际取值（来自当前数据，LLM 选 WHERE 字面量时务必从这里挑）：**
- `department_name`：`动力部` / `炼油一部` / `炼油三部` / `炼油二部` / `炼油公用工程部` / `炼油四部` / `烯烃部` / `环氧芳烃部` / `聚烯烃一部` / `聚烯烃二部` / `钢石气体`
- `area_name`：`乙烯` / `炼油`
- `device_name`：`1#焦化-炼油` / `1#聚丙烯装置ST-化工` / `2#HDPE装置-化工` / `2#催化-炼油` / `2#柴油加氢-炼油` / `2#焦化-炼油` / `2#聚丙烯装置JPP-化工` / `3#催化-炼油` / `3#柴油加氢-炼油` / `3#聚丙烯装置-化工` / `EO/EG装置-化工` / `HDPE装置-化工` / `LLDPE装置-化工` / `乙烯装置-化工` / `余热发电-炼油` / `加氢裂化-炼油` / `反应进料泵P6102A` / `反应进料泵P6102B` / `干气提浓-炼油` / `热电联产装置-化工` …（共 24 个）
- `update_by`：`1`

### 表 `special_unit_record`

| 字段 | 类型 | 主键 | 可空 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | int | ✓ | N | 主键 |
| `task_id` | int |  | Y | 关联任务id |
| `equipment_id` | varchar(255) |  | Y | 设备编码 |
| `device_name` | varchar(255) |  | Y | 装置名 |
| `analyse_result` | text |  | Y | 分析结果 |
| `analyse_type` | varchar(255) |  | Y | 分析类型（运行部/设备工程部....） |
| `create_by` | varchar(255) |  | Y | 创建人 |
| `create_time` | datetime |  | Y | 创建时间 |
| `update_by` | varchar(255) |  | Y | 更新人 |
| `update_time` | datetime |  | Y | 更新时间 |
| `del_flag` | varchar(255) |  | Y | 删除标志 |
| `remark` | varchar(255) |  | Y | 备注 |

**列实际取值（来自当前数据，LLM 选 WHERE 字面量时务必从这里挑）：**
- `equipment_id`：`203298592` / `203298619`
- `device_name`：`热电联产装置-化工`
- `analyse_type`：`DSB` / `SBGCB`

### 表 `special_unit_record_sign`
> 特护任务检查结果签字记录表

| 字段 | 类型 | 主键 | 可空 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | int | ✓ | N | 主键 |
| `task_id` | int |  | Y | 关联任务id |
| `equipment_id` | varchar(255) |  | Y | 设备编码 |
| `device_name` | varchar(255) |  | Y | 装置名 |
| `sign_id` | varchar(100) |  | Y | 签名id |
| `sign_img` | longtext |  | Y | 签名图片 |
| `sign_type` | varchar(255) |  | Y | 签名类型（运行部/设备工程部....） |
| `create_by` | varchar(255) |  | Y | 创建人 |
| `create_time` | datetime |  | Y | 创建时间 |
| `update_by` | varchar(255) |  | Y | 更新人 |
| `update_time` | datetime |  | Y | 更新时间 |
| `del_flag` | varchar(255) |  | Y | 删除标志 |
| `remark` | varchar(255) |  | Y | 备注 |

**列实际取值（来自当前数据，LLM 选 WHERE 字面量时务必从这里挑）：**
- `equipment_id`：`203298592` / `203298619`
- `device_name`：`热电联产装置-化工`
- `sign_type`：`DSB` / `SBGCB`

### 表 `statistics`

| 字段 | 类型 | 主键 | 可空 | 含义 |
| --- | --- | --- | --- | --- |
| `specialty` | varchar(255) |  | Y | 专业 |
| `operation_department` | varchar(255) |  | Y | 运行部 |
| `executions_required` | varchar(255) |  | Y | 应执行数 |
| `total_transactions` | varchar(255) |  | Y | 事务总数 |
| `executed` | varchar(255) |  | Y | 已执行 |
| `under_execution` | varchar(255) |  | Y | 执行中 |
| `triggered` | varchar(255) |  | Y | 已触发 |
| `completed` | varchar(255) |  | Y | 已完成 |

### 表 `trace`

| 字段 | 类型 | 主键 | 可空 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | int | ✓ | N | 自增id |
| `create_time` | datetime |  | Y | 创建时间 |
| `modify_time` | datetime |  | Y | 修改时间 |
| `module` | varchar(255) |  | Y | 业务模块 |
| `operate_type` | varchar(255) |  | Y | 操作类型（增，删，改） |
| `refer_id` | varchar(255) |  | Y | 关联id |
| `refer_type` | varchar(255) |  | Y | 业务关联类型（缺陷，项目，作业，作业票，通知单） |
| `user_id` | varchar(255) |  | Y | 用户id |
| `value` | text |  | Y | 修改值 |
| `ip` | varchar(255) |  | Y | 使用者的ip地址 |
| `properties` | varchar(255) |  | Y | 其他 |
| `source` | varchar(255) |  | Y | 来源 |

**列实际取值（来自当前数据，LLM 选 WHERE 字面量时务必从这里挑）：**
- `module`：`任务审批` / `任务执行` / `定时事务删除` / `定时事务添加` / `定时任务时间修改` / `导表修改` / `插入任务` / `新增定时事务`
- `operate_type`：`DELETE` / `INSERT` / `UPDATE`
- `refer_type`：`事务` / `任务`

### 表 `user_to_role`

| 字段 | 类型 | 主键 | 可空 | 含义 |
| --- | --- | --- | --- | --- |
| `user_zhsh` | varchar(255) |  | Y | 账号唯一id，对应统一身份认证 |
| `role_name` | varchar(255) |  | Y | 角色 |

### 表 `users`

| 字段 | 类型 | 主键 | 可空 | 含义 |
| --- | --- | --- | --- | --- |
| `user_id` | int | ✓ | N | 自增主键 |
| `username` | varchar(255) |  | Y | 账号名称 |
| `password` | varchar(255) |  | Y | 账号密码 |
| `user_zhsh` | varchar(255) |  | N | 账号唯一id，对应统一身份认证 |
| `authority_flag` | int |  | Y | 部门权限：1，装置权限：0 |
| `work_number` | varchar(255) |  | Y | 工号 |

**列实际取值（来自当前数据，LLM 选 WHERE 字面量时务必从这里挑）：**
- `password`：`09090095` / `QWer0843` / `zhsh.123456`
- `work_number`：`04170039` / `08150033` / `4B494689`