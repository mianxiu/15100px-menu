const stages = {
  preflight:'启动检查',fixture:'创建隔离临时文档','native-selection-probe':'批量图层读取核验',
  'idle-read':'闲置后的菜单读取','fixed-layer-label':'固定图层标签','fixed-layer-read':'固定图层菜单读取',
  'preview-commit-undo':'预览确认与一次撤销','preview-cancel':'预览取消恢复','grow-layer':'新增图层',
  'growing-layer-read':'新增图层菜单读取','select-many':'准备多选','multi-selection-read':'多选菜单读取',
  'select-shape':'恢复形状选择',finish:'关闭测试文档',cleanup:'原测试文档收尾',idle:'闲置观察'
};
export function stabilityIssue(test={}) {
  if(test.phase==='cleaned')return null;
  const problem=test.cleanup_problem || test.problem || (test.error?{
    message:'自动测试未完成',hint:'已保留原始错误和阶段，请导出报告；不会自动重发操作。',detail:test.error,stage:test.stage
  }:null);
  if(!problem)return null;
  return {...problem,stage:stages[problem.stage] || problem.stage || '启动检查'};
}
