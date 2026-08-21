package org.jrba.rulesengine.rule.simple;

import static java.util.Objects.isNull;
import static java.util.Optional.ofNullable;
import static org.jrba.rulesengine.constants.MVELParameterConstants.FACTS;
import static org.jrba.rulesengine.constants.RuleTypeConstants.DEFAULT_CHAIN_RULE;
import static org.jrba.rulesengine.types.ruletype.AgentRuleTypeEnum.CHAIN;

import java.io.Serializable;

import org.jeasy.rules.api.Facts;
import org.jrba.agentmodel.domain.node.AgentNode;
import org.jrba.agentmodel.domain.props.AgentProps;
import org.jrba.rulesengine.RulesController;
import org.jrba.rulesengine.rest.domain.RuleRest;
import org.jrba.rulesengine.rule.AgentBasicRule;
import org.jrba.rulesengine.rule.AgentRule;
import org.jrba.rulesengine.rule.AgentRuleDescription;
import org.jrba.rulesengine.ruleset.RuleSet;
import org.jrba.rulesengine.ruleset.RuleSetFacts;
import org.mvel2.MVEL;

import lombok.Getter;

/**
 * Abstract class defining  a rule which after successful execution, triggers once evaluation of the given rule set.
 *
 * @param <E> type of node connected to the Agent
 * @param <T> type of properties of Agent
 */
@Getter
public class AgentChainRule<T extends AgentProps, E extends AgentNode<T>> extends AgentBasicRule<T, E> implements
		Serializable {

	private final RuleSet ruleSet;

	/**
	 * Copy constructor.
	 *
	 * @param rule rule that is to be copied
	 */
	public AgentChainRule(final AgentChainRule<T, E> rule) {
		super(rule);
		this.ruleSet = ofNullable(rule.getRuleSet()).map(RuleSet::new).orElse(null);
	}

	/**
	 * Constructor
	 *
	 * @param controller rules controller connected to the agent
	 * @param priority   priority of the rule execution
	 * @param ruleSet    currently executed rule set
	 */
	protected AgentChainRule(final RulesController<T, E> controller, final int priority, final RuleSet ruleSet) {
		super(controller, priority);
		this.ruleSet = ruleSet;
	}

	/**
	 * Constructor
	 *
	 * @param controller rules controller connected to the agent
	 * @param ruleSet    currently executed rule set
	 */
	protected AgentChainRule(final RulesController<T, E> controller, final RuleSet ruleSet) {
		super(controller);
		this.ruleSet = ruleSet;
	}

	/**
	 * Constructor
	 *
	 * @param ruleRest rest representation of agent rule
	 * @param ruleSet  currently executed rule set
	 */
	public AgentChainRule(final RuleRest ruleRest, final RuleSet ruleSet) {
		super(ruleRest);
		this.ruleSet = ruleSet;
	}

	@Override
	public void execute(final Facts facts) {
		if (isNull(executeExpression)) {
			this.executeRule((RuleSetFacts) facts);
		} else {
			initialParameters.replace(FACTS, facts);
			MVEL.executeExpression(executeExpression, initialParameters);
		}
		controller.fire((RuleSetFacts) facts);
	}

	@Override
	public AgentRuleDescription initializeRuleDescription() {
		return new AgentRuleDescription(DEFAULT_CHAIN_RULE,
				"default chain rule",
				"default implementation of a rule that iteratively performs rules evaluation");
	}

	@Override
	public String getAgentRuleType() {
		return CHAIN.getType();
	}

	@Override
	public AgentRule copy() {
		return new AgentChainRule<>(this);
	}
}
