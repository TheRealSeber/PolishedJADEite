package org.jrba.utils.yellowpages;

import static jade.domain.DFService.createSubscriptionMessage;
import static jade.domain.DFService.keepRegistered;
import static java.util.Collections.emptyMap;
import static java.util.Collections.emptySet;
import static java.util.stream.Collectors.toMap;
import static org.slf4j.LoggerFactory.getLogger;

import java.util.Arrays;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.slf4j.Logger;

import jade.core.AID;
import jade.core.Agent;
import jade.domain.DFService;
import jade.domain.FIPAAgentManagement.DFAgentDescription;
import jade.domain.FIPAAgentManagement.ServiceDescription;
import jade.domain.FIPAException;
import jade.lang.acl.ACLMessage;

/**
 * Service which provides the methods used in communication with the DF
 */
public class YellowPagesRegister {

	private static final Logger logger = getLogger(YellowPagesRegister.class);

	private YellowPagesRegister() {
	}

	/**
	 * Method prepares AID of DF of given platform
	 *
	 * @param address    address of the platform host
	 * @param platformId platform identifier
	 * @return AID of DF agent
	 */
	public static AID prepareDF(final String address, final String platformId) {
		final AID df = new AID("df@" + platformId, AID.ISGUID);
		df.addAddresses(address);
		return df;
	}

	/**
	 * Method registers the given agent in the DF
	 *
	 * @param agent       agent that is to be registered
	 * @param dfAID       identifier od the DF
	 * @param serviceType type of the service to be registered
	 * @param serviceName name of the service to be registered
	 * @param ownership   name of the owner to be registered (applicable only for agents with hierarchical organization)
	 */
	public static void register(Agent agent, AID dfAID, String serviceType, String serviceName, String ownership) {
		try {
			DFService.register(agent, dfAID,
					prepareAgentDescription(agent.getAID(), serviceType, serviceName, ownership));
			keepRegistered(agent, dfAID, prepareAgentDescription(agent.getAID(), serviceType, serviceName, ownership),
					null);
		} catch (FIPAException e) {
			logger.info("Couldn't register {} in the directory facilitator", agent);
		}
	}

	/**
	 * Method registers the given agent in the DF
	 *
	 * @param agent       agent that is to be registered
	 * @param dfAID       identifier od the DF
	 * @param serviceType type of the service to be registered
	 * @param serviceName name of the service to be registered
	 */
	public static void register(Agent agent, AID dfAID, String serviceType, String serviceName) {
		try {
			DFService.register(agent, dfAID, prepareAgentDescription(agent.getAID(), serviceType, serviceName));
		} catch (FIPAException e) {
			logger.info("Couldn't register {} in the directory facilitator", agent);
		}
	}

	/**
	 * Method deregisters the given agent in the DF
	 *
	 * @param agent agent that is to be deregistered
	 * @param dfAID identifier od the DF
	 */
	public static void deregister(Agent agent, AID dfAID) {
		try {
			DFService.deregister(agent, dfAID);
		} catch (FIPAException e) {
			logger.info("Couldn't deregister {} from the directory facilitator", agent);
		}
	}

	/**
	 * Method deregisters the given agent in the DF
	 *
	 * @param agent       agent that is to be deregistered
	 * @param dfAID       identifier od the DF
	 * @param serviceType type of the service to be deregistered
	 * @param serviceName name of the service to be deregistered
	 */
	public static void deregister(Agent agent, AID dfAID, String serviceType, String serviceName) {
		try {
			DFService.deregister(agent, dfAID, prepareAgentDescription(agent.getAID(), serviceType, serviceName));
		} catch (FIPAException e) {
			logger.info("Couldn't deregister {} from the directory facilitator", agent);
		}
	}

	/**
	 * Method deregisters the given agent in the DF
	 *
	 * @param agent       agent that is to be deregistered
	 * @param dfAID       identifier od the DF
	 * @param serviceType type of the service to be deregistered
	 * @param serviceName name of the service to be deregistered
	 * @param ownership   name of the owner to be deregistered (applicable only for agents with hierarchical organization)
	 */
	public static void deregister(Agent agent, AID dfAID, String serviceType, String serviceName, String ownership) {
		try {
			DFService.deregister(agent, dfAID,
					prepareAgentDescription(agent.getAID(), serviceType, serviceName, ownership));
		} catch (FIPAException e) {
			logger.info("Couldn't deregister {} in the directory facilitator", agent);
		}
	}

	/**
	 * Method searches the DF for the agents with given service type
	 *
	 * @param agent       agent which is searching through the DF
	 * @param dfAID       identifier od the DF
	 * @param serviceType type of the service to be searched
	 * @return list of agent addresses found in DF
	 */
	public static Set<AID> search(Agent agent, AID dfAID, String serviceType) {
		try {
			return Arrays.stream(DFService.search(agent, dfAID, prepareAgentDescriptionTemplate(serviceType)))
					.map(DFAgentDescription::getName).collect(Collectors.toSet());
		} catch (FIPAException e) {
			logger.info("Haven't found any agents because {}", e.getMessage());
		}

		return emptySet();
	}

	/**
	 * Method subscribes a given agent service for the subscriber agent.
	 *
	 * @param subscriber  agent subscribing given service
	 * @param dfAID       identifier od the DF
	 * @param serviceType type of the service to be subscribed
	 * @return subscription ACLMessage
	 */
	public static ACLMessage prepareSubscription(final Agent subscriber, final AID dfAID, final String serviceType) {
		return createSubscriptionMessage(subscriber, dfAID,
				prepareAgentDescriptionTemplate(serviceType), null);
	}

	/**
	 * Method subscribes a given agent service for the subscriber agent.
	 *
	 * @param subscriber  agent subscribing given service
	 * @param dfAID       identifier od the DF
	 * @param serviceType type of the service to be subscribed
	 * @param ownership   name of the owner to be searched (applicable only for agents with hierarchical organization)
	 * @return subscription ACLMessage
	 */
	public static ACLMessage prepareSubscription(final Agent subscriber, final AID dfAID, final String serviceType,
			final String ownership) {
		return createSubscriptionMessage(subscriber, dfAID,
				prepareAgentDescriptionTemplate(serviceType, ownership), null);
	}

	/**
	 * Method decodes the received notification and retrieves agent service information
	 *
	 * @param inform notification received from DF
	 * @return Map of agent AIDS along with status if the agent service is registered/deregistered
	 */
	public static Map<AID, Boolean> decodeSubscription(final ACLMessage inform) {
		try {
			return Arrays.stream(DFService.decodeNotification(inform.getContent()))
					.collect(toMap(DFAgentDescription::getName, desc -> desc.getAllServices().hasNext()));
		} catch (FIPAException e) {
			logger.info("An error occurred while decoding the notification: {}", e.getMessage());
		}

		return emptyMap();
	}

	private static DFAgentDescription prepareAgentDescription(AID aid, String serviceType, String serviceName,
			String ownership) {
		var agentDescription = new DFAgentDescription();
		agentDescription.setName(aid);
		agentDescription.addServices(prepareDescription(serviceType, serviceName, ownership));
		return agentDescription;
	}

	private static DFAgentDescription prepareAgentDescription(AID aid, String serviceType, String serviceName) {
		var agentDescription = new DFAgentDescription();
		agentDescription.setName(aid);
		agentDescription.addServices(prepareDescription(serviceType, serviceName));
		return agentDescription;
	}

	private static ServiceDescription prepareDescription(String serviceType, String serviceName, String ownership) {
		var serviceDescription = new ServiceDescription();
		serviceDescription.setType(serviceType);
		serviceDescription.setName(serviceName);
		serviceDescription.setOwnership(ownership);
		return serviceDescription;
	}

	private static ServiceDescription prepareDescription(String serviceType, String serviceName) {
		var serviceDescription = new ServiceDescription();
		serviceDescription.setType(serviceType);
		serviceDescription.setName(serviceName);
		return serviceDescription;
	}

	private static ServiceDescription prepareDescription(String serviceType) {
		var serviceDescription = new ServiceDescription();
		serviceDescription.setType(serviceType);
		return serviceDescription;
	}

	private static ServiceDescription prepareDescriptionOwnership(String serviceType, String ownership) {
		var serviceDescription = new ServiceDescription();
		serviceDescription.setType(serviceType);
		serviceDescription.setOwnership(ownership);
		return serviceDescription;
	}

	private static DFAgentDescription prepareAgentDescriptionTemplate(String serviceType, String ownership) {
		var template = new DFAgentDescription();
		template.addServices(prepareDescriptionOwnership(serviceType, ownership));
		return template;
	}

	private static DFAgentDescription prepareAgentDescriptionTemplate(String serviceType) {
		var template = new DFAgentDescription();
		template.addServices(prepareDescription(serviceType));
		return template;
	}
}
