"""User-facing context for an original test failure; never authorizes a retry."""


def describe(error, stage, pending=False):
    raw = str(error)[:500]
    if pending:
        code, message, hint = ('result-pending', '原请求结果仍待核对',
                               '等待原请求终态；不要重复开始测试或关闭测试文档。')
    elif raw in ('已停止后续测试','已停止尚未提交的收尾'):
        code, message, hint = ('user-stopped', '已按要求停止后续测试',
                               '保留原测试报告；原请求结束后可核验并结束测试文档。')
    elif 'An owned test document is still retained' in raw:
        code, message, hint = ('fixture-retained', '上次测试的临时文档仍保留',
                               '先导出报告，再使用“结束上次测试文档”；不要重复创建测试。')
    elif any(x in raw for x in ('Test ownership unavailable', 'Test document changed',
                                'Original documents changed', 'Test selection/history changed',
                                'Test target changed', 'Test document set changed')):
        code, message, hint = ('target-changed', '测试文档、选择或历史已变化',
                               '已停止后续操作。保留现场并导出报告；收尾仍须核验原测试所有权。')
    elif 'Single undo' in raw:
        code, message, hint = ('undo-mismatch', '一次撤销核验未通过',
                               '已停止后续操作，保留测试文档供检查并导出报告。')
    elif any(x in raw for x in ('Native selection', 'native selection', 'native tree',
                                'native layer', 'native document', 'native read', 'native fallback')):
        code, message, hint = ('layer-read-failed', '图层读取核验未通过',
                               '导出报告查看读取阶段；这不表示修改已成功，也不会自动重试。')
    elif '前台' in raw:
        code, message, hint = ('foreground-changed', '测试已因前台范围保护停止',
                               '回到PS或后台管理窗口后，先结束保留的原测试文档，再重新开始。')
    else:
        code, message, hint = ('test-failed', '自动测试未完成',
                               '已保留原始错误和阶段，请导出报告；不会自动重发操作。')
    return {'code': code, 'message': message, 'hint': hint, 'stage': stage, 'detail': raw}
