# 物理化学机理链 v1：供研究智能体复用

研究入口：calculate_mechanistic_chain。模型ID capillary-sphere-sink-v1。

这不是依据辅料名称输出系数的工具。先读取冻结基准与实际变化方案，所有同时变化和补差均纳入；不得更改API或原方。

## 四层交付
1. 原粉几何：S=sum(m*s), Vsolid=sum(m/rho)。球形近似s=6/(rho*d32)，使用SI；d90、筛目不能充当d32。
2. 制粒结构/界面：实际干颗粒及填充床的epsilon,k,rp,L,theta。将纯粉面积相加不能取得辊压颗粒外面积；恒MgSt质量不能证明恒覆盖。Young/Young-Dupre为理想界面关系，实际theta须有同条件依据。
3. 毛细进液：B=4*k*gamma*cos(theta)/(mu*epsilon*rp)，tw=L^2/B。theta计算转弧度。刚性均匀平板内均匀API在深度比例u的暴露时刻为lag+tw*u^2。
4. 漏槽缩粒：td=rho_API*h*d_API/(2*D*Cs)，F(age)=0(age<=0)，否则1-max(1-age/td,0)^3。Q(t)=100*integral_0^1 F(t-lag-tw*u^2)du。积分按已暴露与已完全溶解边界分段，128点Gauss-Legendre求积。

其物理意义是不同深度API依次开始溶解；不声称复现Ferdoush & Gonzalez 2024的完整群体平衡/粒度分布算法。

## 输入合同
baseline_id与variant_id必须来自本轮冻结输入。API质量由服务器冻结处方读取。mass_basis写明溶解度和API质量一致的证据；assumptions说明刚性、近似漏槽、球形单分散、暴露后不再受黏结限制及其适用性。
arms恰好两个，顺序为baseline、variant。各含label、parameters。每个参数含value,unit,basis(source/measurement/explicit_hypothesis),source_id,locator,applicability,source_quote。来源/实测参数须有逐字原文摘录，SI换算在applicability记录；假设不能标作实测。不得缺参调用，不代填未知值。
参数及单位：permeability m2；surface_tension N/m；contact_angle deg；viscosity Pa.s；porosity 1；pore_radius m；path_length m；diffusivity m2/s；solubility kg/m3；api_density kg/m3；diffusion_layer m；api_diameter m；medium_volume m3；shell_lag s。
times_s严格递增且非负。至少两点。只有Cs*V/M0>=10才计算；这是当前近似漏槽实现的限制，不是所有模型的通用定律。

## 参数缺失时继续研究
按制粒后结构、润滑后润湿、API本征溶解三个包检索；分别记录source/measurement/hypothesis，原始单位转换及适用工艺。若缺少相同工艺物性，保存候选分支与缺口，不将纯粉性质或其他药物参数套用到目标。
淀粉显著膨胀、持续黏结包埋、API团聚、动态孔隙、非漏槽或pH漂移均要求扩展模型。不得用本工具忽略这些作用后宣称目标预测。
实验分开识别润湿时标与API溶解时标，不能把所有参数同时拟合到一条Q曲线。目标实测参与后称校准，不能称独立验证。

## 本项目可确切写出的变化
诺氟沙星当前MCC19.6→4.6mg、预胶化淀粉14→29mg；其余质量不变。同批原粉物性不变的条件下DeltaS=0.015*(s_starch-s_MCC) m2，s单位m2/g。这不等于干颗粒外面积变化，也不是药物溶出差值。

## 文献与验证
Ferdoush & Gonzalez 2024，DOI10.1016/j.ijpharm.2024.124635，作者PDF https://web.ics.purdue.edu/~gonza226/papers/FerdoushGonzalez2024.pdf ，本轮已读取建模结构；不迁移片剂/其它药物参数。
Markl等2017，作者库 https://strathprints.strath.ac.uk/63791/1/Markl_etal_IJOP_2017_Mathematical_modelling_of_liquid_transport_in_swelling.pdf ，提供动态孔隙/膨胀扩展路线，当前实现未包含这些状态方程。
软件测试 tests/test_mechanistic_chain.py：纯合成参数，仅检验数学实现、守恒、零变化、独立积分复核、粒径/接触角条件响应及非法输入。不得将测试参数导入项目处方或药学预测。

## 来源结构复算
save_source_metric允许quantity=ribbon_solid_fraction，unit=1。仅用于原文明示的压带固相分数，逐组绑定连续原句及定位。系统确定性计算epsilon=1-SF与G=epsilon^3/(1-epsilon)^2；模型ribbon-porosity-geometry-v1。G比不是无条件渗透率比，须另有Sv及K0的变化依据，不外推来源淀粉百分比至目标MCC替换。本程序不会因此自动填充目标孔隙率或渗透率。句末小数例如0.76.可正确识别；不从版本号或千位分隔数字截取局部值。
# 来源复算优先与目标类比（2026-09-24）

不要把取得目标完整物性或目标实验作为开始建模的前置条件。先检索其他药物同类辅料变化的完整对照，以工艺和中间物性可比性优先，不限同药或同BCS。四项状态分别交付：来源数据、来源模型复算、目标迁移、目标验证。

左侧交付原始数据点及来源身份，方程/单位、实际计算值、逐点残差、校准误差和验证状态。来源经验拟合不能称独立验证或辅料独立贡献。有混杂或仅作者概括值时明确保留，不伪称配对批均值。

右侧绑定本次冻结基准与方案ID，计算真实变化坐标，逐项说明API、辅料牌号、组成、工艺、介质差异。区分可迁移结构、待修正系数及假设。可先交付局部物性条件敏感性，不必等整方溶出；不能把局部量直接换算为溶出率。假设情景无概率权重，不称置信区间；超出来源坐标域显式标外推。

已实现网页 source-porosity-analogy-v1 案例：Chang2008已归档且quantity=ribbon_solid_fraction的0/5/20% Starch1500点，ε=1−SF，再最小二乘拟合ε=a+bx。目标仅探索Δε=η b Δx，η=-1/0/1为显式反向/不迁移/同斜率假设。页面实时计算并可导出，不能声称研究工具已调用该计算器或这些η来自实验。来源无MCC、API不同，跨组合数据，目标尚无校准；此案例不能替代继续检索真正配对来源。后续同类资料仍使用save_source_metric保存真实点及出处，未知横坐标不能猜。其他物料不套该斜率。
