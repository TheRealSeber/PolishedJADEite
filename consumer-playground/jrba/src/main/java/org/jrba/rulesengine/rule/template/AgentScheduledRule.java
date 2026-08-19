package org.jrba.rulesengine.rule.template;

import static java.lang.String.format;
import static java.util.Objects.isNull;
import static java.util.Objects.nonNull;
import static org.jrba.rulesengine.constants.FactTypeConstants.TRIGGER_TIME;
import static org.jrba.rulesengine.constants.MVELParameterConstants.FACTS;
import static org.jrba.rulesengine.constants.RuleTypeConstants.DEFAULT_SCHEDULE_RULE;
import static org.jrba.rulesengine.types.rulesteptype.RuleStepTypeEnum.SCHEDULED_EXECUTE_ACTION_STEP;
import static org.jrba.rulesengine.types.rulesteptype.RuleStepTypeEnum.SCHEDULED_SELECT_TIME_STEP;
import static org.jrba.rulesengine.types.ruletype.AgentRuleTypeEnum.SCHEDULED;

import java.io.Serializable;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;

import org.jrba.agentmodel.domain.node.AgentNode;
import org.jrba.agentmodel.domain.props.AgentProps;
import org.jrba.rulesengine.RulesController;
import org.jrba.rulesengine.rest.domain.ScheduledRuleRest;
import org.jrba.rulesengine.rule.AgentBasicRule;
import org.jrba.rulesengine.rule.AgentRule;
import org.jrba.rulesengine.rule.AgentRuleDescription;
import org.jrba.rulesengine.ruleset.RuleSetFacts;
import org.mvel2.MVEL;

import lombok.Getter;

/**
 * Abstract class defining structure of a rule which is executed once at the time specified by the user.
 *
 * @param <E> type of node connected to the Agent
 * @param <T> type of properties of Agent
 */
@Getter
public class AgentScheduledRule<T extends AgentProps, E extends AgentNode<T>> extends AgentBasicRule<T, E> {

	protected Serializable expressionSpecifyTime;
	protected Serializable expressionHandleActionTrigger;
	protected Serializable expressionEvaluateBeforeTrigger;

	/**
	 * Copy constructor.
	 *
	 * @param rule rule that is to be copied
	 */
	public AgentScheduledRule(final AgentScheduledRule<T, E> rule) {
		super(rule);
		this.expressionSpecifyTime = rule.getExpressionSpecifyTime();
		this.expressionHandleActionTrigger = rule.getExpressionHandleActionTrigger();
		this.expressionEvaluateBeforeTrigger = rule.getExpressionEvaluateBeforeTrigger();
	}

	/**
	 * Constructor
	 *
	 * @param controller rules controller connected to the agent
	 */
	protected AgentScheduledRule(final RulesController<T, E> controller) {
		super(controller);
		initializeSteps();
	}

	/**
	 * Constructor
	 *
	 * @param ruleRest rest representation of agent rule
	 */
	public AgentScheduledRule(final ScheduledRuleRest ruleRest) {
		super(ruleRest);
		if (nonNull(ruleRest.getEvaluateBeforeTrigger())) {
			this.expressionEvaluateBeforeTrigger = MVEL.compileExpression(
					imports + " " + ruleRest.getEvaluateBeforeTrigger());
		}
		if (nonNull(ruleRest.getSpecifyTime())) {
			this.expressionSpecifyTime = MVEL.compileExpression(imports + " " + ruleRest.getSpecifyTime());
		}
		if (nonNull(ruleRest.getHandleActionTrigger())) {
			this.expressionHandleActionTrigger = MVEL.compileExpression(
					imports + " " + ruleRest.getHandleActionTrigger());
		}
		initializeSteps();
	}

	/**
	 * Method assigns a list of scheduler rule steps.
	 */
	public void initializeSteps() {
		stepRules = new ArrayList<>(List.of(new SpecifyExecutionTimeRule(), new HandleActionTriggerRule()));
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

	@Override
	public String getAgentRuleType() {
		return SCHEDULED.getType();
	}

	/**
	 * Method specify time at which behaviour is to be executed.
	 *
	 * @param facts facts with additional parameters
	 * @return Date specifying when the rule will be triggered
	 */
	protected Date specifyTime(final RuleSetFacts facts) {
		return Date.from(Instant.now());
	}

	/**
	 * Method evaluates if the action should have effects.
	 *
	 * @param facts facts with additional parameters
	 * @return boolean indicating if the rule's action should be executed
	 */
	protected boolean evaluateBeforeTrigger(final RuleSetFacts facts) {
		return true;
	}

	/**
	 * Method executed when specific time of behaviour execution is reached.
	 *
	 * @param facts facts with additional parameters
	 */
	protected void handleActionTrigger(final RuleSetFacts facts) {
		// TO BE OVERRIDDEN BY USER
	}

	@Override
	public AgentRuleDescription initializeRuleDescription() {
		return new AgentRuleDescription(DEFAULT_SCHEDULE_RULE,
				"default scheduled rule",
				"default implementation of a rule that is executed at a scheduled time");
	}

	@Override
	public AgentRule copy() {
		return new AgentScheduledRule<>(this);
	}

	// RULE EXECUTED WHEN EXECUTION TIME IS TO BE SELECTED
	class SpecifyExecutionTimeRule extends AgentBasicRule<T, E> {

		public SpecifyExecutionTimeRule() {
			super(AgentScheduledRule.this.controller);
			this.isRuleStep = true;
		}

		@Override
		public void executeRule(final RuleSetFacts facts) {
			if (nonNull(AgentScheduledRule.this.initialParameters)) {
				AgentScheduledRule.this.initialParameters.replace(FACTS, facts);
			}
			final Date period = isNull(expressionSpecifyTime) ?
					specifyTime(facts) :
					(Date) MVEL.executeExpression(expressionSpecifyTime, AgentScheduledRule.this.initialParameters);
			facts.put(TRIGGER_TIME, period);
		}

		@Override
		public AgentRuleDescription initializeRuleDescription() {
			return new AgentRuleDescription(AgentScheduledRule.this.ruleType, SCHEDULED_SELECT_TIME_STEP,
					format("%s - specify action execution time", AgentScheduledRule.this.name),
					"rule performed when behaviour execution time is to be selected");
		}

		@Override
		public AgentRule copy() {
			return new SpecifyExecutionTimeRule();
		}
	}

	// RULE EXECUTED WHEN BEHAVIOUR ACTION IS EXECUTED
	class HandleActionTriggerRule extends AgentBasicRule<T, E> {

		public HandleActionTriggerRule() {
			super(AgentScheduledRule.this.controller);
			this.isRuleStep = true;
		}

		@Override
		public boolean evaluateRule(final RuleSetFacts facts) {
			if (nonNull(AgentScheduledRule.this.initialParameters)) {
				AgentScheduledRule.this.initialParameters.replace(FACTS, facts);
			}
			return isNull(expressionEvaluateBeforeTrigger) ?
					evaluateBeforeTrigger(facts) :
					(boolean) MVEL.executeExpression(expressionEvaluateBeforeTrigger,
							AgentScheduledRule.this.initialParameters);
		}

		@Override
		public void executeRule(final RuleSetFacts facts) {
			if (nonNull(AgentScheduledRule.this.initialParameters)) {
				AgentScheduledRule.this.initialParameters.replace(FACTS, facts);
			}
			if (isNull(expressionHandleActionTrigger)) {
				handleActionTrigger(facts);
			} else {
				MVEL.executeExpression(expressionHandleActionTrigger, AgentScheduledRule.this.initialParameters);
			}
		}

		@Override
		public AgentRuleDescription initializeRuleDescription() {
			return new AgentRuleDescription(AgentScheduledRule.this.ruleType, SCHEDULED_EXECUTE_ACTION_STEP,
					format("%s - execute action", AgentScheduledRule.this.name),
					"rule that executes action at specific time");
		}

		@Override
		public AgentRule copy() {
			return new HandleActionTriggerRule();
		}
	}

}
