package org.jrba.rulesengine.ruleset;

import static java.util.Optional.ofNullable;
import static org.jrba.rulesengine.constants.FactTypeConstants.RULE_STEP;
import static org.jrba.rulesengine.constants.FactTypeConstants.RULE_TYPE;
import static org.jrba.rulesengine.mvel.MVELRuleMapper.getRuleForType;

import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.stream.Stream;

import org.jeasy.rules.api.Rules;
import org.jeasy.rules.api.RulesEngine;
import org.jeasy.rules.core.DefaultRulesEngine;
import org.jrba.rulesengine.RulesController;
import org.jrba.rulesengine.rest.domain.RuleSetRest;
import org.jrba.rulesengine.rule.AgentRule;

import lombok.Getter;
import lombok.Setter;

/**
 * Class represents rule set facilitating reasoning of given agents
 */
@Getter
public class RuleSet {

	protected List<AgentRule> agentRules;
	protected RulesEngine rulesEngine;
	protected RulesController<?, ?> rulesController;
	protected boolean callInitializeRules;
	@Setter
	private String name;

	/**
	 * Constructor
	 *
	 * @param ruleSetRest JSON Rest object from which rule set is to be created
	 */
	public RuleSet(final RuleSetRest ruleSetRest) {
		this.rulesEngine = new DefaultRulesEngine();
		this.name = ruleSetRest.getName();
		this.callInitializeRules = false;
		this.agentRules = ofNullable(ruleSetRest.getRules())
				.map(ruleRests -> ruleRests.stream().map(ruleRest -> getRuleForType(ruleRest, this)))
				.map(Stream::toList)
				.map(ArrayList::new)
				.orElse(new ArrayList<>());
	}

	/**
	 * Constructor
	 *
	 * @param ruleSet rule set to create copy from
	 */
	public RuleSet(final RuleSet ruleSet) {
		this.rulesEngine = new DefaultRulesEngine();
		this.name = ruleSet.getName();
		this.agentRules = new ArrayList<>(ruleSet.getAgentRules());
		this.rulesController = ruleSet.getRulesController();
		this.callInitializeRules = false;
	}

	/**
	 * Constructor
	 *
	 * @param ruleSet    ruleSet template from ruleSet map
	 * @param controller controller which runs given rule set
	 */
	public RuleSet(final RuleSet ruleSet, final RulesController<?, ?> controller) {
		this.rulesEngine = new DefaultRulesEngine();
		this.rulesController = controller;
		this.name = ruleSet.getName();

		if (!ruleSet.callInitializeRules) {
			this.agentRules = ruleSet.getAgentRules().stream()
					.filter(rule -> rule.getAgentType().equals(controller.getAgentProps().getAgentType()))
					.map(AgentRule::copy)
					.toList();
			agentRules.forEach(agentRule -> agentRule.connectToController(controller));
		} else {
			this.agentRules = ruleSet.initializeRules(controller);
		}
	}

	/**
	 * Constructor
	 *
	 * @param name name of the rule set
	 */
	protected RuleSet(final String name, final boolean callInitializeRules) {
		this.rulesEngine = new DefaultRulesEngine();
		this.agentRules = new ArrayList<>();
		this.name = name;
		this.callInitializeRules = callInitializeRules;
	}

	/**
	 * Constructor
	 *
	 * @param name       name of the rule set
	 * @param agentRules list of agent rules (initially not connected with the controller)
	 */
	protected RuleSet(final String name, final List<AgentRule> agentRules) {
		this.rulesEngine = new DefaultRulesEngine();
		this.agentRules = agentRules;
		this.name = name;
	}

	/**
	 * Method fires agent rule set for a set of facts
	 *
	 * @param facts set of facts based on which actions are going to be taken
	 */
	public void fireRuleSet(final RuleSetFacts facts) {
		final Rules rules = new Rules();
		agentRules.stream()
				.filter(agentRule -> agentRule.getRuleType().equals(facts.get(RULE_TYPE)))
				.map(AgentRule::getRules)
				.flatMap(Collection::stream)
				.filter(agentRule -> agentRule.isRuleStep()
						? agentRule.getStepType().equals(facts.get(RULE_STEP))
						: agentRule.getRuleType().equals(facts.get(RULE_TYPE)))
				.forEach(rules::register);

		if (!rules.isEmpty()) {
			rulesEngine.fire(rules, facts);
		}
	}

	/**
	 * Method that can be optionally overridden to initialize rules
	 * IMPORTANT! Rules should be already sorted based on the agent type
	 * (type of the agent can be retrieved from the rulesController)
	 *
	 * @param rulesController controller which runs given rule set
	 * @return list of agent rules
	 */
	protected List<AgentRule> initializeRules(RulesController<?, ?> rulesController) {
		return new ArrayList<>();
	}

}
