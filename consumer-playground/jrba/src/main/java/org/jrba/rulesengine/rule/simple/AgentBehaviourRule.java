package org.jrba.rulesengine.rule.simple;

import static java.util.Objects.isNull;
import static java.util.Objects.nonNull;
import static java.util.Optional.ofNullable;
import static org.jrba.rulesengine.constants.MVELParameterConstants.FACTS;
import static org.jrba.rulesengine.constants.RuleTypeConstants.INITIALIZE_BEHAVIOURS_RULE;
import static org.jrba.rulesengine.types.ruletype.AgentRuleTypeEnum.BEHAVIOUR;

import java.io.Serializable;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import org.jrba.agentmodel.domain.node.AgentNode;
import org.jrba.agentmodel.domain.props.AgentProps;
import org.jrba.rulesengine.RulesController;
import org.jrba.rulesengine.rest.domain.BehaviourRuleRest;
import org.jrba.rulesengine.rule.AgentBasicRule;
import org.jrba.rulesengine.rule.AgentRule;
import org.jrba.rulesengine.rule.AgentRuleDescription;
import org.jrba.rulesengine.ruleset.RuleSetFacts;
import org.mvel2.MVEL;

import jade.core.behaviours.Behaviour;
import lombok.Getter;

/**
 * Abstract class defining structure of a rule which adds rule-set-specific behaviours to the agent.
 *
 * @param <E> type of node connected to the Agent
 * @param <T> type of properties of Agent
 */
@Getter
public class AgentBehaviourRule<T extends AgentProps, E extends AgentNode<T>> extends AgentBasicRule<T, E> implements
		Serializable {

	protected List<Serializable> expressionsBehaviours;

	/**
	 * Copy constructor.
	 *
	 * @param rule rule that is to be copied
	 */
	public AgentBehaviourRule(final AgentBehaviourRule<T, E> rule) {
		super(rule);
		this.expressionsBehaviours = ofNullable(rule.getExpressionsBehaviours())
				.map(ArrayList::new)
				.orElse(null);
	}

	/**
	 * Constructor
	 *
	 * @param controller rules controller connected to the agent
	 */
	protected AgentBehaviourRule(final RulesController<T, E> controller) {
		super(controller);
	}

	/**
	 * Constructor
	 *
	 * @param ruleRest rest representation of agent rule
	 */
	public AgentBehaviourRule(final BehaviourRuleRest ruleRest) {
		super(ruleRest);
		if (nonNull(ruleRest.getBehaviours())) {
			this.expressionsBehaviours = ruleRest.getBehaviours().stream()
					.map(behaviourExp -> MVEL.compileExpression(imports + " " + behaviourExp))
					.toList();
		}
	}

	/**
	 * Method initialize set of behaviours that are to be added.
	 *
	 * @return Set of agent behaviours
	 */
	protected Set<Behaviour> initializeBehaviours() {
		return new HashSet<>();
	}

	@Override
	public void executeRule(final RuleSetFacts facts) {
		if (nonNull(this.initialParameters)) {
			this.initialParameters.replace(FACTS, facts);
		}

		final Set<Behaviour> behaviours;

		if (isNull(expressionsBehaviours)) {
			behaviours = initializeBehaviours();
		} else {
			behaviours = this.expressionsBehaviours.stream()
					.map(exp -> (Behaviour) MVEL.executeExpression(exp, this.initialParameters))
					.collect(Collectors.toSet());
		}
		behaviours.forEach(agent::addBehaviour);
	}

	@Override
	public AgentRuleDescription initializeRuleDescription() {
		return new AgentRuleDescription(INITIALIZE_BEHAVIOURS_RULE,
				"initialize agent behaviours",
				"when rule set is selected and agent is set-up, it adds set of default behaviours");
	}

	@Override
	public String getAgentRuleType() {
		return BEHAVIOUR.getType();
	}

	@Override
	public AgentRule copy() {
		return new AgentBehaviourRule<>(this);
	}
}
