package pw.model;

import java.io.Serializable;

public record FlightProposal(
        String providerName,
        int totalPriceEur
) implements Serializable {
}