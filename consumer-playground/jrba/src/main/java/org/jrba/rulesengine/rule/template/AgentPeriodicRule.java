package org.jrba.rulesengine.rule.template;

import static java.lang.Long.parseLong;
import static java.lang.String.format;
import static java.util.Objects.isNull;
import static java.util.Objects.nonNull;
import static org.jrba.rulesengine.constants.FactTypeConstants.TRIGGER_PERIOD;
import static org.jrba.rulesengine.constants.MVELParameterConstants.FACTS;
import static org.jrba.rulesengine.constants.RuleTypeConstants.DEFAULT_PERIODIC_RULE;
import static org.jrba.rulesengine.types.rulesteptype.RuleStepTypeEnum.PERIODIC_EXECUTE_ACTION_STEP;
import static org.jrba.rulesengine.types.rulesteptype.RuleStepTypeEnum.PERIODIC_SELECT_PERIOD_STEP;
import static org.jrba.rulesengine.types.ruletype.AgentRuleTypeEnum.PERIODIC;

import java.io.Serializable;
import java.util.ArrayList;
import java.util.List;

import org.jrba.agentmodel.domain.node.AgentNode;
import org.jrba.agentmodel.domain.props.AgentProps;
import org.jrba.rulesengine.RulesController;
import org.jrba.rulesengine.rest.domain.PeriodicRuleRest;
import org.jrba.rulesengine.rule.AgentBasicRule;
import org.jrba.rulesengine.rule.AgentRule;
import org.jrba.rulesengine.rule.AgentRuleDescription;
import org.jrba.rulesengine.ruleset.RuleSetFacts;
import org.mvel2.MVEL;

import lombok.Getter;

/**
 * Abstract class defining structure of a rule which handles default periodic behaviour.
 *
 * @param <E> type of node connected to the Agent
 * @param <T> type of properties of Agent
 */
@Getter
public class AgentPeriodicRule<T extends AgentProps, E extends AgentNode<T>> extends AgentBasicRule<T, E> {

	protected Serializable expressionSpecifyPeriod;
	protected Serializable expressionHandleActionTrigger;
	protected Serializable expressionEvaluateBeforeTrigger;

	/**
	 * Copy constructor.
	 *
	 * @param rule rule that is to be copied
	 */
	public AgentPeriodicRule(final AgentPeriodicRule<T, E> rule) {
		super(rule);
		this.expressionSpecifyPeriod = rule.getExpressionSpecifyPeriod();
		this.expressionHandleActionTrigger = rule.getExpressionHandleActionTrigger();
		this.expressionEvaluateBeforeTrigger = rule.getExpressionEvaluateBeforeTrigger();
	}

	/**
	 * Constructor
	 *
	 * @param controller rules controller connected to the agent
	 */
	protected AgentPeriodicRule(final RulesController<T, E> controller) {
		super(controller);
		initializeSteps();
	}

	/**
	 * Constructor
	 *
	 * @param ruleRest rest representation of agent rule
	 */
	public AgentPeriodicRule(final PeriodicRuleRest ruleRest) {
		super(ruleRest);
		if (nonNull(ruleRest.getEvaluateBeforeTrigger())) {
			this.expressionEvaluateBeforeTrigger = MVEL.compileExpression(
					imports + " " + ruleRest.getEvaluateBeforeTrigger());
		}
		if (nonNull(ruleRest.getSpecifyPeriod())) {
			this.expressionSpecifyPeriod = MVEL.compileExpression(imports + " " + ruleRest.getSpecifyPeriod());
		}
		if (nonNull(ruleRest.getHandleActionTrigger())) {
			this.expressionHandleActionTrigger = MVEL.compileExpression(
					imports + " " + ruleRest.getHandleActionTrigger());
		}
		initializeSteps();
	}

	/**
	 * Method evaluates if the action should have effects.
	 *
	 * @param facts facts with additional parameters
	 * @return boolean indicating if the rule's action should be triggered
	 */
	protected boolean evaluateBeforeTrigger(final RuleSetFacts facts) {
		return true;
	}

	@Override
	public String getAgentRuleType() {
		return PERIODIC.getType();
	}

	/**
	 * Method assigns a list of periodic rule steps.
	 */
	public void initializeSteps() {
		stepRules = new ArrayList<>(List.of(new SpecifyPeriodRule(), new HandleActionTriggerRule()));
	}

	@Override
	public List<AgentRule> getRules() {
		return stepRules;
	}

	@Override
	public void connectToController(final RulesController<?, ?> rulesController) {
		super.connectToController(rulesController);
		stepRules.forEach(rule -> rule.connectToController(rulesController));
	}

	/**
	 * Method specify period after which behaviour is to be executed (in milliseconds).
	 *
	 * @return number of milliseconds after which the rule evaluation is to be triggered.
	 */
	protected long specifyPeriod() {
		return 0;
	}

	/**
	 * Method executed when time after which action is to be triggerred has passed.
	 *
	 * @param facts facts with additional parameters
	 */
	protected void handleActionTrigger(final RuleSetFacts facts) {
		// TO BE OVERRIDDEN BY USER
	}

	@Override
	public AgentRuleDescription initializeRuleDescription() {
		return new AgentRuleDescription(DEFAULT_PERIODIC_RULE,
				"default periodic rule",
				"default implementation of a rule that is being periodically evaluated");
	}

	@Override
	public AgentRule copy() {
		return new AgentPeriodicRule<>(this);
	}

	// RULE EXECUTED WHEN PERIOD IS TO BE SELECTED
	class SpecifyPeriodRule extends AgentBasicRule<T, E> {

		public SpecifyPeriodRule() {
			super(AgentPeriodicRule.this.controller);
			this.isRuleStep = true;
		}

		@Override
		public void executeRule(final RuleSetFacts facts) {
			if (nonNull(AgentPeriodicRule.this.initialParameters)) {
				AgentPeriodicRule.this.initialParameters.replace(FACTS, facts);
			}

			final long period = isNull(expressionSpecifyPeriod)
					? specifyPeriod()
					: parseLong(MVEL.executeExpression(expressionSpecifyPeriod,
					AgentPeriodicRule.this.initialParameters).toString());
			facts.put(TRIGGER_PERIOD, period);
		}

		@Override
		public AgentRuleDescription initializeRuleDescription() {
			return new AgentRuleDescription(AgentPeriodicRule.this.ruleType, PERIODIC_SELECT_PERIOD_STEP,
					format("%s - specify action period", AgentPeriodicRule.this.name),
					"rule performed when behaviour period is to be selected");
		}

		@Override
		public AgentRule copy() {
			return new SpecifyPeriodRule();
		}
	}

	// RULE EXECUTED WHEN BEHAVIOUR ACTION IS EXECUTED
	class HandleActionTriggerRule extends AgentBasicRule<T, E> {

		public HandleActionTriggerRule() {
			super(AgentPeriodicRule.this.controller);
			this.isRuleStep = true;
		}

		@Override
		public boolean evaluateRule(final RuleSetFacts facts) {
			if (nonNull(AgentPeriodicRule.this.initialParameters)) {
				AgentPeriodicRule.this.initialParameters.replace(FACTS, facts);
			}

			return isNull(expressionEvaluateBeforeTrigger) ?
					evaluateBeforeTrigger(facts) :
					(boolean) MVEL.executeExpression(expressionEvaluateBeforeTrigger,
							AgentPeriodicRule.this.initialParameters);
		}

		@Override
		public void executeRule(final RuleSetFacts facts) {
			if (nonNull(AgentPeriodicRule.this.initialParameters)) {
				AgentPeriodicRule.this.initialParameters.replace(FACTS, facts);
			}

			if (isNull(expressionHandleActionTrigger)) {
				handleActionTrigger(facts);
			} else {
				MVEL.executeExpression(expressionHandleActionTrigger, AgentPeriodicRule.this.initialParameters);
			}
		}

		@Override
		public AgentRuleDescription initializeRuleDescription() {
			return new AgentRuleDescription(AgentPeriodicRule.this.ruleType, PERIODIC_EXECUTE_ACTION_STEP,
					format("%s - execute action", AgentPeriodicRule.this.name),
					"rule that executes action after specified period of time has passed");
		}

		@Override
		public AgentRule copy() {
			return new HandleActionTriggerRule();
		}
	}

}
