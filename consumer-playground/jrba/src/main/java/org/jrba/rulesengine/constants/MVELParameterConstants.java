package org.jrba.rulesengine.constants;

/**
 * Class with constants describing available fact types
 */
public class MVELParameterConstants {

	// RULES CONTROLLER PARAMETERS
	/**
	 * Parameter specifying rules controller.
	 */
	public static final String RULES_CONTROLLER = "controller";


	// LOGGER PARAMETERS
	/**
	 * Parameter specifying logger.
	 */
	public static final String LOGGER = "logger";


	// AGENT PARAMETERS
	/**
	 * Parameter specifying a agent.
	 */
	public static final String AGENT = "agent";

	/**
	 * Parameter specifying the collection of agents.
	 */
	public static final String AGENTS = "agents";

	/**
	 * Parameter specifying agent's properties.
	 */
	public static final String AGENT_PROPS = "agentProps";

	/**
	 * Parameter specifying agent's node.
	 */
	public static final String AGENT_NODE = "agentNode";


	// FACTS PARAMETERS
	/**
	 * Parameter specifying rule's facts.
	 */
	public static final String FACTS = "facts";


	// CFP RULE PARAMETERS
	/**
	 * Parameter specifying received proposals.
	 */
	public static final String ALL_PROPOSALS = "allProposals";

	/**
	 * Parameter specifying the best selected proposal.
	 */
	public static final String BEST_PROPOSAL = "bestProposal";

	/**
	 * Parameter specifying newly received proposal.
	 */
	public static final String NEW_PROPOSAL = "newProposal";

	/**
	 * Parameter specifying proposal that is to be rejected.
	 */
	public static final String PROPOSAL_TO_REJECT = "proposalToReject";


	// SUBSCRIPTION RULE PARAMETERS
	/**
	 * Parameter specifying agents that added their service.
	 */
	public static final String ADDED_AGENTS = "addedAgents";

	/**
	 * Parameter specifying agents that removed their service.
	 */
	public static final String REMOVED_AGENTS = "removedAgents";


	// PROPOSAL RULE PARAMETERS
	/**
	 * Parameter specifying message accepting the proposal.
	 */
	public static final String ACCEPT_MESSAGE = "acceptMessage";

	/**
	 * Parameter specifying message rejecting the proposal.
	 */
	public static final String REJECT_MESSAGE = "rejectMessage";


	// REQUEST RULE PARAMETERS
	/**
	 * Parameter specifying request's inform response.
	 */
	public static final String INFORM = "inform";

	/**
	 * Parameter specifying request's refuse response.
	 */
	public static final String REFUSE = "refuse";

	/**
	 * Parameter specifying request's failure response.
	 */
	public static final String FAILURE = "failure";

	/**
	 * Parameter specifying request's inform responses.
	 */
	public static final String INFORM_RESULTS = "informResults";

	/**
	 * Parameter specifying request's failure responses.
	 */
	public static final String FAILURE_RESULTS = "failureResults";


	// SINGLE MESSAGE RULE PARAMETERS
	/**
	 * Parameter specifying received message.
	 */
	public static final String MESSAGE = "message";
}
