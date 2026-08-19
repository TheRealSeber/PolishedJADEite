package org.jrba.rulesengine.rule;

import static java.util.Objects.isNull;
import static java.util.Objects.nonNull;
import static java.util.Optional.ofNullable;
import static org.jrba.rulesengine.constants.FactTypeConstants.RULE_TYPE;
import static org.jrba.rulesengine.constants.MVELParameterConstants.AGENT;
import static org.jrba.rulesengine.constants.MVELParameterConstants.AGENT_NODE;
import static org.jrba.rulesengine.constants.MVELParameterConstants.AGENT_PROPS;
import static org.jrba.rulesengine.constants.MVELParameterConstants.FACTS;
import static org.jrba.rulesengine.constants.MVELParameterConstants.LOGGER;
import static org.jrba.rulesengine.constants.MVELParameterConstants.RULES_CONTROLLER;
import static org.jrba.rulesengine.types.ruletype.AgentRuleTypeEnum.BASIC;
import static org.jrba.rulesengine.mvel.MVELObjectType.getObjectForType;
import static org.slf4j.LoggerFactory.getLogger;

import java.io.Serializable;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.apache.tomcat.util.buf.StringUtils;
import org.jeasy.rules.api.Facts;
import org.jeasy.rules.core.BasicRule;
import org.jrba.agentmodel.domain.node.AgentNode;
import org.jrba.agentmodel.domain.props.AgentProps;
import org.jrba.rulesengine.RulesController;
import org.jrba.rulesengine.rest.domain.RuleRest;
import org.jrba.rulesengine.ruleset.RuleSetFacts;
import org.mvel2.MVEL;
import org.slf4j.Logger;

import jade.core.Agent;
import lombok.EqualsAndHashCode;
import lombok.Getter;
import lombok.NoArgsConstructor;

/**
 * Abstract class defining structure of a rule, executed within an agent's behaviour.
 *
 * @param <E> type of node connected to the Agent
 * @param <T> type of properties of Agent
 */
@Getter
@EqualsAndHashCode(callSuper = true)
@NoArgsConstructor
@SuppressWarnings("unchecked")
public class AgentBasicRule<T extends AgentProps, E extends AgentNode<T>> extends BasicRule
		implements AgentRule, Serializable {

	static final Logger logger = getLogger(AgentBasicRule.class);
	protected RulesController<T, E> controller;
	protected T agentProps;
	protected E agentNode;
	protected Agent agent;
	protected String agentType;
	protected String ruleType;
	protected String subRuleType;
	protected String stepType;
	protected boolean isRuleStep;
	protected List<AgentRule> stepRules;
	protected Map<String, Object> initialParameters;
	protected String imports;
	protected Serializable executeExpression;
	protected Serializable evaluateExpression;

	/**
	 * Copy constructor.
	 *
	 * @param rule rule that is to be copied
	 */
	public AgentBasicRule(final AgentBasicRule<T, E> rule) {
		this.agentType = rule.getAgentType();
		this.ruleType = rule.getRuleType();
		this.subRuleType = rule.getSubRuleType();
		this.stepType = rule.getStepType();
		this.isRuleStep = rule.isRuleStep();
		this.controller = rule.getController();
		this.agentProps = rule.getAgentProps();
		this.agentNode = rule.getAgentNode();
		this.agent = rule.getAgent();
		this.imports = rule.getImports();
		this.executeExpression = rule.getExecuteExpression();
		this.evaluateExpression = rule.getEvaluateExpression();
		this.name = rule.getName();
		this.description = rule.getDescription();
		this.priority = rule.getPriority();

		if (nonNull(rule.getInitialParameters())) {
			this.initialParameters = new HashMap<>(rule.getInitialParameters());
		}
		if(nonNull(rule.getStepRules())) {
			this.stepRules = new ArrayList<>(rule.getStepRules().stream().map(AgentRule::copy).toList());
		}
	}

	/**
	 * Constructor
	 *
	 * @param ruleRest rest representation of an agent rule
	 */
	public AgentBasicRule(final RuleRest ruleRest) {
		super();
		this.isRuleStep = nonNull(ruleRest.getStepType());
		this.name = ruleRest.getName();
		this.description = ruleRest.getDescription();
		this.ruleType = ruleRest.getType();
		this.subRuleType = ruleRest.getSubType();
		this.stepType = ruleRest.getStepType();
		this.initialParameters = new HashMap<>();
		this.priority = ofNullable(ruleRest.getPriority()).orElse(super.priority);
		this.agentType = ruleRest.getAgentType();

		if (nonNull(ruleRest.getInitialParams())) {
			ruleRest.getInitialParams().forEach((key, value) -> initialParameters.put(key, getObjectForType(value)));
		}

		imports = StringUtils.join(ruleRest.getImports(), ' ');
		imports = imports + " import org.slf4j.MDC;";
		imports = imports + " import org.jrba.rulesengine.constants.LoggingConstants;";
		imports = imports.trim();
		if (nonNull(ruleRest.getExecute())) {
			this.executeExpression = MVEL.compileExpression(imports + " " + ruleRest.getExecute());
		}
		if (nonNull(ruleRest.getEvaluate())) {
			this.evaluateExpression = MVEL.compileExpression(imports + " " + ruleRest.getEvaluate());
		}
	}

	/**
	 * Constructor
	 *
	 * @param rulesController rules controller connected to the agent
	 */
	protected AgentBasicRule(final RulesController<T, E> rulesController) {
		if (nonNull(rulesController)) {
			this.agent = rulesController.getAgent();
			this.agentType = rulesController.getAgentProps().getAgentType();
			this.agentProps = rulesController.getAgentProps();
			this.agentNode = rulesController.getAgentNode();
			this.controller = rulesController;
			this.isRuleStep = false;
		}

		final AgentRuleDescription ruleDescription = initializeRuleDescription();
		this.name = ruleDescription.ruleName();
		this.stepType = ruleDescription.stepType();
		this.description = ruleDescription.ruleDescription();
		this.ruleType = ruleDescription.ruleType();
		this.subRuleType = ruleDescription.subType();
	}

	/**
	 * Constructor
	 *
	 * @param rulesController rules controller connected to the agent
	 * @param priority        priority of the rule execution
	 */
	protected AgentBasicRule(final RulesController<T, E> rulesController, final int priority) {
		this(rulesController);
		this.priority = priority;
	}

	/**
	 * Method connects agent rule with controller
	 *
	 * @param rulesController rules controller connected to the agent
	 */
	@Override
	public void connectToController(final RulesController<?, ?> rulesController) {
		this.agent = rulesController.getAgent();
		this.agentProps = (T) rulesController.getAgentProps();
		this.agentNode = (E) rulesController.getAgentNode();
		this.controller = (RulesController<T, E>) rulesController;
		this.agentType = rulesController.getAgentProps().getAgentType();

		if (nonNull(initialParameters)) {
			initialParameters.putIfAbsent(AGENT, agent);
			initialParameters.putIfAbsent(AGENT_PROPS, agentProps);
			initialParameters.putIfAbsent(AGENT_NODE, agentNode);
			initialParameters.putIfAbsent(RULES_CONTROLLER, controller);
			initialParameters.putIfAbsent(LOGGER, logger);
			initialParameters.putIfAbsent(FACTS, null);
		}
	}

	@Override
	public String getAgentRuleType() {
		return BASIC.getType();
	}

	@Override
	public boolean evaluateRule(final RuleSetFacts facts) {
		return ruleType.equals(facts.get(RULE_TYPE));
	}

	@Override
	public boolean evaluate(final Facts facts) {
		if (isNull(evaluateExpression)) {
			return evaluateRule((RuleSetFacts) facts);
		} else {
			initialParameters.replace(FACTS, facts);
			return (boolean) MVEL.executeExpression(evaluateExpression, initialParameters);
		}
	}

	@Override
	public void execute(final Facts facts) {
		if (isNull(executeExpression)) {
			executeRule((RuleSetFacts) facts);
		} else {
			initialParameters.replace(FACTS, facts);
			MVEL.executeExpression(executeExpression, initialParameters);
		}
	}

	@Override
	public AgentRule copy() {
		return new AgentBasicRule<>(this);
	}
}
