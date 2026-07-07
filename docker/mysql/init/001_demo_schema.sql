SET NAMES utf8mb4;
SET time_zone = '+08:00';

CREATE TABLE IF NOT EXISTS `user` (
    user_id INT PRIMARY KEY,
    username VARCHAR(255) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    authority_flag INT NOT NULL COMMENT '0=engineer, 1=admin'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO `user` (user_id, username, password, authority_flag) VALUES
    (1, 'admin', 'admin', 1),
    (2, 'engineer', 'engineer', 0)
ON DUPLICATE KEY UPDATE
    username = VALUES(username),
    password = VALUES(password),
    authority_flag = VALUES(authority_flag);

CREATE TABLE IF NOT EXISTS affair (
    affair_id VARCHAR(64) PRIMARY KEY,
    affair_name VARCHAR(255) NOT NULL,
    affair_type VARCHAR(100),
    specialty VARCHAR(100),
    operation_department VARCHAR(100),
    status VARCHAR(50),
    created_at DATETIME NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS affair_task (
    task_id VARCHAR(64) PRIMARY KEY,
    associated_affair_id VARCHAR(64) NOT NULL,
    task_name VARCHAR(255) NOT NULL,
    task_properties VARCHAR(100),
    operation_department VARCHAR(100),
    execution_department VARCHAR(100),
    professional VARCHAR(100),
    device_name VARCHAR(255),
    device_code VARCHAR(100),
    job_content TEXT,
    module VARCHAR(100),
    upload_auto VARCHAR(20),
    status VARCHAR(50),
    created_at DATETIME NOT NULL,
    INDEX idx_affair_task_affair (associated_affair_id),
    INDEX idx_affair_task_department (operation_department, execution_department),
    CONSTRAINT fk_affair_task_affair
        FOREIGN KEY (associated_affair_id) REFERENCES affair(affair_id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO affair (
    affair_id, affair_name, affair_type, specialty,
    operation_department, status, created_at
) VALUES
    ('AF-1001', '常减压装置巡检事务', '巡检', '仪表', '炼油一部', '运行中', '2026-06-01 09:00:00'),
    ('AF-1002', '加氢装置检修事务', '检修', '设备', '炼油二部', '待处理', '2026-06-02 10:30:00'),
    ('AF-1003', '罐区隐患整改事务', '隐患', '安全', '储运部', '已完成', '2026-06-03 14:15:00')
ON DUPLICATE KEY UPDATE
    affair_name = VALUES(affair_name),
    affair_type = VALUES(affair_type),
    specialty = VALUES(specialty),
    operation_department = VALUES(operation_department),
    status = VALUES(status);

INSERT INTO affair_task (
    task_id, associated_affair_id, task_name, task_properties,
    operation_department, execution_department, professional,
    device_name, device_code, job_content, module, upload_auto,
    status, created_at
) VALUES
    (
        'TK-2001', 'AF-1001', '检查流量计 FT-101 零点漂移', '巡检任务',
        '炼油一部', '仪表班', '仪表', '常减压流量计', 'FT-101',
        '核对现场显示、DCS 趋势和校验记录', '巡检', '是',
        '运行中', '2026-06-01 09:30:00'
    ),
    (
        'TK-2002', 'AF-1002', '更换 P-201A 机械密封', '检修任务',
        '炼油二部', '设备班', '设备', '加氢进料泵', 'P-201A',
        '确认隔离、置换、检修票证和试运记录', '检修', '否',
        '待处理', '2026-06-02 11:00:00'
    ),
    (
        'TK-2003', 'AF-1003', '整改罐区可燃气报警器遮挡', '隐患任务',
        '储运部', '安全班', '安全', '可燃气报警器', 'GA-301',
        '清理遮挡物并复测报警响应', '隐患', '是',
        '已完成', '2026-06-03 15:00:00'
    )
ON DUPLICATE KEY UPDATE
    task_name = VALUES(task_name),
    task_properties = VALUES(task_properties),
    operation_department = VALUES(operation_department),
    execution_department = VALUES(execution_department),
    professional = VALUES(professional),
    device_name = VALUES(device_name),
    device_code = VALUES(device_code),
    job_content = VALUES(job_content),
    module = VALUES(module),
    upload_auto = VALUES(upload_auto),
    status = VALUES(status);

CREATE TABLE IF NOT EXISTS agent_conversation (
    id BIGINT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    title VARCHAR(255),
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    expires_at DATETIME,
    deleted_at DATETIME,
    delete_status VARCHAR(50),
    retention_policy VARCHAR(50),
    INDEX idx_agent_conversation_user_updated (user_id, deleted_at, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS agent_message (
    id BIGINT PRIMARY KEY,
    conversation_id BIGINT NOT NULL,
    role VARCHAR(50),
    content TEXT,
    created_at DATETIME NOT NULL,
    deleted_at DATETIME,
    INDEX idx_agent_message_conversation_created (conversation_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS agent_conversation_summary (
    conversation_id BIGINT PRIMARY KEY,
    summary_text MEDIUMTEXT NOT NULL,
    summarized_until_message_id BIGINT,
    covered_message_id BIGINT COMMENT 'Deprecated compatibility alias; use summarized_until_message_id.',
    source_message_count INT NOT NULL DEFAULT 0,
    summary_version INT NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    INDEX idx_conversation_summary_updated (updated_at),
    INDEX idx_conversation_summary_pointer (summarized_until_message_id),
    CONSTRAINT fk_conversation_summary_conversation
        FOREIGN KEY (conversation_id) REFERENCES agent_conversation(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_conversation_summary_pointer
        FOREIGN KEY (summarized_until_message_id) REFERENCES agent_message(id)
        ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS agent_tool_log (
    id BIGINT PRIMARY KEY,
    conversation_id BIGINT,
    user_id BIGINT,
    tool_name VARCHAR(100),
    input_summary TEXT,
    output_summary TEXT,
    status VARCHAR(50),
    error_message TEXT,
    created_at DATETIME NOT NULL,
    expires_at DATETIME,
    INDEX idx_agent_tool_log_created (created_at),
    INDEX idx_agent_tool_log_user (user_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS agent_audit_log (
    id BIGINT PRIMARY KEY,
    user_id BIGINT,
    action_type VARCHAR(100),
    target_type VARCHAR(100),
    target_id VARCHAR(100),
    action_detail TEXT,
    ip_address VARCHAR(100),
    created_at DATETIME NOT NULL,
    INDEX idx_agent_audit_log_created (created_at),
    INDEX idx_agent_audit_log_user (user_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS user_memory (
    id BIGINT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    memory_type VARCHAR(64) NOT NULL,
    content TEXT NOT NULL,
    source VARCHAR(64) NOT NULL DEFAULT 'manual',
    confidence DECIMAL(5,4) NOT NULL DEFAULT 1.0000,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    metadata_json JSON,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    expires_at DATETIME,
    INDEX idx_user_memory_user_status (user_id, status, updated_at),
    INDEX idx_user_memory_type_status (memory_type, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS memory_event (
    id BIGINT PRIMARY KEY,
    memory_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    event_type VARCHAR(32) NOT NULL,
    actor_id BIGINT,
    reason VARCHAR(255) NOT NULL DEFAULT '',
    payload_json JSON,
    created_at DATETIME NOT NULL,
    INDEX idx_memory_event_memory_created (memory_id, created_at),
    CONSTRAINT fk_memory_event_memory
        FOREIGN KEY (memory_id) REFERENCES user_memory(id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO agent_audit_log (
    id, user_id, action_type, target_type, target_id,
    action_detail, ip_address, created_at
) VALUES
    (900001, 1, 'demo_init', 'system', 'docker', 'Docker demo schema initialized', '127.0.0.1', NOW())
ON DUPLICATE KEY UPDATE
    action_detail = VALUES(action_detail),
    created_at = VALUES(created_at);
