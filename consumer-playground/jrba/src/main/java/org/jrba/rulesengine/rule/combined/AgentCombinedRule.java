package org.jrba.rulesengine.rule.combined;

import static java.util.Collections.emptyList;
import static java.util.Collections.singletonList;
import static java.util.Optional.ofNullable;
import static org.jrba.rulesengine.constants.RuleTypeConstants.DEFAULT_COMBINED_RULE;
import static org.jrba.rulesengine.mvel.MVELRuleMapper.getRuleForType;
import static org.jrba.rulesengine.types.ruletype.AgentRuleTypeEnum.BASIC;
import static org.jrba.rulesengine.types.ruletype.AgentRuleTypeEnum.COMBINED;

import java.io.Serializable;
import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;
import java.util.function.Predicate;

import org.jeasy.rules.api.Facts;
import org.jeasy.rules.support.composite.ActivationRuleGroup;
import org.jeasy.rules.support.composite.UnitRuleGroup;
import org.jrba.agentmodel.domain.node.AgentNode;
import org.jrba.agentmodel.domain.props.AgentProps;
import org.jrba.rulesengine.RulesController;
import org.jrba.rulesengine.rest.domain.CombinedRuleRest;
import org.jrba.rulesengine.rule.AgentBasicRule;
import org.jrba.rulesengine.rule.AgentRule;
import org.jrba.rulesengine.rule.AgentRuleDescription;
import org.jrba.rulesengine.ruleset.RuleSet;
import org.jrba.rulesengine.ruleset.RuleSetFacts;
import org.jrba.rulesengine.types.rulecombinationtype.AgentCombinedRuleType;

import lombok.Getter;
import lombok.Setter;

/**
 * Abstract class defining structure of a rule which combines multiple rules and defines how they should be handled.
 *
 * @param <E> type of node connected to the Agent
 * @param <T> type of properties of Agent
 */
@Getter
public class AgentCombinedRule<T extends AgentProps, E extends AgentNode<T>> extends AgentBasicRule<T, E> implements
		Serializable {

	protected final RuleSet ruleSet;
	protected final String combinationType;
	protected final List<AgentRule> rulesToCombine;

	/**
	 * Copy constructor.
	 *
	 * @param rule rule that is to be copied
	 */
	public AgentCombinedRule(final AgentCombinedRule<T, E> rule) {
		super(rule);
		this.ruleSet = ofNullable(rule.getRuleSet()).map(RuleSet::new).orElse(null);
		this.combinationType = rule.getCombinationType();
		this.rulesToCombine = new ArrayList<>(ofNullable(rule.getRulesToCombine())
				.orElse(emptyList()).stream()
				.map(AgentRule::copy).toList());
	}

	/**
	 * Constructor
	 *
	 * @param controller      rules controller connected to the agent
	 * @param combinationType way in which agent rules are to be combined
	 */
	protected AgentCombinedRule(final RulesController<T, E> controller, final AgentCombinedRuleType combinationType) {
		super(controller);
		this.combinationType = combinationType.getType();
		this.ruleSet = null;
		this.rulesToCombine = new ArrayList<>(constructRules());
	}

	/**
	 * Constructor
	 *
	 * @param controller      rules controller connected to the agent
	 * @param combinationType way in which agent rules are to be combined
	 * @param priority        priority of rule execution
	 */
	protected AgentCombinedRule(final RulesController<T, E> controller, final AgentCombinedRuleType combinationType,
			final int priority) {
		super(controller, priority);
		this.combinationType = combinationType.getType();
		this.ruleSet = null;
		this.rulesToCombine = new ArrayList<>(constructRules());
	}

	/**
	 * Constructor
	 *
	 * @param controller      rules controller connected to the agent
	 * @param combinationType way in which agent rules are to be combined
	 * @param rulesToCombine  list of nested rules
	 */
	protected AgentCombinedRule(final RulesController<T, E> controller, final AgentCombinedRuleType combinationType,
			final List<AgentRule> rulesToCombine) {
		super(controller);
		this.combinationType = combinationType.getType();
		this.ruleSet = null;
		this.rulesToCombine = new ArrayList<>(rulesToCombine);
	}

	/**
	 * Constructor
	 *
	 * @param controller      rules controller connected to the agent
	 * @param ruleSet         currently executed rule set
	 * @param combinationType way in which agent rules are to be combined
	 */
	protected AgentCombinedRule(final RulesController<T, E> controller, final RuleSet ruleSet,
			final AgentCombinedRuleType combinationType) {
		super(controller);
		this.combinationType = combinationType.getType();
		this.ruleSet = ruleSet;
		this.rulesToCombine = new ArrayList<>(constructRules());
	}

	/**
	 * Constructor
	 *
	 * @param ruleRest rest representation of agent rule
	 * @param ruleSet  currently executed rule set
	 */
	public AgentCombinedRule(final CombinedRuleRest ruleRest, final RuleSet ruleSet) {
		super(ruleRest);
		this.combinationType = ruleRest.getCombinedRuleType().getType();
		this.ruleSet = ruleSet;
		this.rulesToCombine = new ArrayList<>(ruleRest.getRulesToCombine().stream()
				.map(rule -> getRuleForType(rule, ruleSet))
				.toList());
	}

	@Override
	public void connectToController(final RulesController<?, ?> rulesController) {
		super.connectToController(rulesController);
		rulesToCombine.forEach(rule -> rule.connectToController(controller));
	}

	@Override
	public String getAgentRuleType() {
		return COMBINED.getType();
	}

	@Override
	public List<AgentRule> getRules() {
		return (switch (combinationType) {
			case "EXECUTE_FIRST" -> singletonList(constructExecuteFirstGroup());
			case "EXECUTE_ALL" -> singletonList(constructExecuteAllGroup());
			default -> new ArrayList<>();
		});
	}

	@Override
	public AgentRule copy() {
		return new AgentCombinedRule<>(this);
	}

	/**
	 * Method returns nested combined rules
	 *
	 * @return nested rules
	 */
	public List<String> getNestedRules() {
		return rulesToCombine.stream().map(AgentRule::getSubRuleType).toList();
	}

	@Override
	public boolean evaluateRule(final RuleSetFacts facts) {
		return true;
	}

	/**
	 * Method construct set of rules that are to be combined.
	 *
	 * @return list of AgentRule used in the given combination
	 */
	protected List<AgentRule> constructRules() {
		return new ArrayList<>();
	}

	private AgentExecuteFirstCombinedRule constructExecuteFirstGroup() {
		final AgentExecuteFirstCombinedRule rulesGroup =
				new AgentExecuteFirstCombinedRule(name, description, this::evaluateRule, this::executeRule);
		rulesToCombine.forEach(rulesGroup::addRule);
		return rulesGroup;
	}

	private AgentExecuteAllCombinedRule constructExecuteAllGroup() {
		final AgentExecuteAllCombinedRule rulesGroup =
				new AgentExecuteAllCombinedRule(name, description, this::evaluateRule, this::executeRule);
		rulesToCombine.forEach(rulesGroup::addRule);
		return rulesGroup;
	}

	@Override
	public AgentRuleDescription initializeRuleDescription() {
		return new AgentRuleDescription(DEFAULT_COMBINED_RULE,
				"default combination rule",
				"default implementation of a rule that consists of multiple nested rules");
	}

	@Setter
	@Getter
	class AgentExecuteAllCombinedRule extends UnitRuleGroup implements AgentRule {

		private final Predicate<RuleSetFacts> preEvaluated;
		private final Consumer<RuleSetFacts> preExecute;

		public AgentExecuteAllCombinedRule(final String name, final String description,
				final Predicate<RuleSetFacts> preEvaluated, final Consumer<RuleSetFacts> preExecute) {
			super(name, description);
			this.preEvaluated = preEvaluated;
			this.preExecute = preExecute;
		}

		public AgentExecuteAllCombinedRule(final AgentExecuteAllCombinedRule rule) {
			super(rule.getName(), rule.getDescription());

			this.preExecute = rule.getPreExecute();
			this.preEvaluated = rule.getPreEvaluated();
		}

		@Override
		public AgentRuleDescription initializeRuleDescription() {
			return AgentCombinedRule.this.initializeRuleDescription();
		}

		@Override
		public boolean evaluate(final Facts facts) {
			if (preEvaluated.test((RuleSetFacts) facts)) {
				preExecute.accept((RuleSetFacts) facts);
			}
			return preEvaluated.test((RuleSetFacts) facts) && super.evaluate(facts);
		}

		@Override
		public AgentRule copy() {
			return new AgentExecuteAllCombinedRule(this);
		}

		@Override
		public String getAgentType() {
			return AgentCombinedRule.this.getAgentType();
		}

		@Override
		public String getAgentRuleType() {
			return BASIC.getType();
		}

		@Override
		public boolean evaluateRule(final RuleSetFacts facts) {
			return this.evaluate(facts);
		}

		@Override
		public String getRuleType() {
			return AgentCombinedRule.this.ruleType;
		}

		@Override
		public String getSubRuleType() {
			return AgentCombinedRule.this.subRuleType;
		}

		@Override
		public String getStepType() {
			return null;
		}

		@Override
		public boolean isRuleStep() {
			return false;
		}
	}

	@Setter
	@Getter
	class AgentExecuteFirstCombinedRule extends ActivationRuleGroup implements AgentRule {

		private final Predicate<RuleSetFacts> preEvaluated;
		private final Consumer<RuleSetFacts> preExecute;

		public AgentExecuteFirstCombinedRule(final String name, final String description,
				final Predicate<RuleSetFacts> preEvaluated, final Consumer<RuleSetFacts> preExecute) {
			super(name, description);
			this.preEvaluated = preEvaluated;
			this.preExecute = preExecute;
		}

		public AgentExecuteFirstCombinedRule(final AgentExecuteFirstCombinedRule rule) {
			super(rule.getName(), rule.getDescription());

			this.preExecute = rule.getPreExecute();
			this.preEvaluated = rule.getPreEvaluated();
		}

		@Override
		public AgentRuleDescription initializeRuleDescription() {
			return AgentCombinedRule.this.initializeRuleDescription();
		}

		@Override
		public boolean evaluate(final Facts facts) {
			if (preEvaluated.test((RuleSetFacts) facts)) {
				preExecute.accept((RuleSetFacts) facts);
				return super.evaluate(facts);
			}
			return false;
		}

		@Override
		public AgentRule copy() {
			return new AgentExecuteFirstCombinedRule(this);
		}

		@Override
		public String getAgentRuleType() {
			return BASIC.getType();
		}

		@Override
		public boolean evaluateRule(final RuleSetFacts facts) {
			return this.evaluate(facts);
		}

		@Override
		public String getRuleType() {
			return AgentCombinedRule.this.ruleType;
		}

		@Override
		public String getSubRuleType() {
			return AgentCombinedRule.this.subRuleType;
		}

		@Override
		public String getStepType() {
			return null;
		}

		@Override
		public String getAgentType() {
			return AgentCombinedRule.this.getAgentType();
		}

		@Override
		public boolean isRuleStep() {
			return false;
		}
	}
}
