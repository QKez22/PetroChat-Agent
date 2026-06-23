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

### 表 `based_info`

| 字段 | 类型 | 主键 | 可空 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | int | ✓ | N | 自增id |
| `ea_id` | varchar(255) |  | Y | 运行部Id |
| `ea_name` | varchar(255) |  | Y | 运行部名，装置名 |
| `ea_title` | varchar(255) |  | Y | 分类 |
| `ea_code` | varchar(255) |  | Y | 代码，设备编码 |
| `ea_parent_ea_code` | varchar(255) |  | Y | 父级代码 |

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

### 表 `equip_archi`

| 字段 | 类型 | 主键 | 可空 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | int | ✓ | N | 自增id |
| `ea_id` | varchar(255) |  | Y | 运行部Id |
| `ea_name` | varchar(255) |  | Y | 运行部名，装置名 |
| `ea_title` | varchar(255) |  | Y | 分类 |
| `ea_code` | varchar(255) |  | Y | 代码 |
| `ea_parent_ea_code` | varchar(255) |  | Y | 父级代码 |

### 表 `equip_archi_backup`

| 字段 | 类型 | 主键 | 可空 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | int | ✓ | N | 自增id |
| `ea_id` | varchar(255) |  | Y | 运行部Id |
| `ea_name` | varchar(255) |  | Y | 运行部名，装置名 |
| `ea_title` | varchar(255) |  | Y | 分类 |
| `ea_code` | varchar(255) |  | Y | 代码 |
| `ea_parent_ea_code` | varchar(255) |  | Y | 父级代码 |

### 表 `equiparchi_to_user`

| 字段 | 类型 | 主键 | 可空 | 含义 |
| --- | --- | --- | --- | --- |
| `ea_id` | varchar(255) |  | Y |  |
| `user_zhsh` | varchar(255) |  | Y |  |

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

### 表 `login_info`

| 字段 | 类型 | 主键 | 可空 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | int | ✓ | N | 自增主键 |
| `user_zhsh` | varchar(255) |  | Y | 账号唯一id，对应统一身份认证 |
| `user_name` | varchar(255) |  | Y | 用户名 |
| `time` | datetime |  | Y | 时间 |
| `state` | int |  | Y | 0：登入，1：登出 |
| `source` | varchar(255) |  | Y | 来源 |

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