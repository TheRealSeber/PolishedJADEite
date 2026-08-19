package org.jrba.rulesengine.constants;

import static java.lang.String.valueOf;
import static org.jrba.rulesengine.constants.FactTypeConstants.RULE_SET_IDX;

import java.util.function.Function;

import org.jeasy.rules.api.Facts;

/**
 * Class contains constants used to handle Log4J logging.
 */
public class LoggingConstants {

	/**
	 * Identifier used to log information based on job identifier.
	 */
	public static final String MDC_JOB_ID = "jobId";

	/**
	 * Identifier used to log information based on rule set identifier.
	 */
	public static final String MDC_RULE_SET_ID = "ruleSetId";

	/**
	 * Identifier used to log information based on agent name.
	 */
	public static final String MDC_AGENT_NAME = "agentName";

	/**
	 * Identifier used to log information based on client name.
	 */
	public static final String MDC_CLIENT_NAME = "clientName";

	/**
	 * Function that select rule set index based on facts.
	 */
	public static final Function<Facts, String> getIdxFromFacts = (facts -> valueOf((int) facts.get(RULE_SET_IDX)));
}
