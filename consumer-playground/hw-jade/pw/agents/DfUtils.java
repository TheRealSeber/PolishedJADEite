package pw.agents;

import jade.core.Agent;
import jade.domain.DFService;
import jade.domain.FIPAAgentManagement.DFAgentDescription;
import jade.domain.FIPAAgentManagement.Property;
import jade.domain.FIPAAgentManagement.ServiceDescription;
import jade.domain.FIPAException;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

final class DfUtils {
    private DfUtils() {
    }

    static void registerService(Agent agent, String serviceType, String serviceName, String ownership) {
        DFAgentDescription dfd = new DFAgentDescription();
        dfd.setName(agent.getAID());

        ServiceDescription sd = new ServiceDescription();
        sd.setType(serviceType);
        sd.setName(serviceName);
        if (ownership != null && !ownership.isBlank()) {
            sd.setOwnership(ownership);
            sd.addProperties(new Property("agency", ownership));
        }
        dfd.addServices(sd);

        try {
            DFService.register(agent, dfd);
        } catch (FIPAException e) {
            throw new IllegalStateException("Unable to register DF service for " + agent.getLocalName(), e);
        }
    }

    static List<DFAgentDescription> searchByType(Agent agent, String serviceType) {
        DFAgentDescription template = new DFAgentDescription();
        ServiceDescription sd = new ServiceDescription();
        sd.setType(serviceType);
        template.addServices(sd);

        try {
            DFAgentDescription[] results = DFService.search(agent, template);
            List<DFAgentDescription> list = new ArrayList<>(results.length);
            Collections.addAll(list, results);
            return list;
        } catch (FIPAException e) {
            throw new IllegalStateException("Unable to query DF for " + serviceType, e);
        }
    }
}