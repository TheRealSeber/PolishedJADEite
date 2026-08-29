package pw.model;

import java.io.Serializable;
import java.util.Objects;

public final class FlightProposal implements Serializable {

    private static final long serialVersionUID = 1L;

    private final String providerName;
    private final int totalPriceEur;

    public FlightProposal(String providerName, int totalPriceEur) {
        this.providerName = providerName;
        this.totalPriceEur = totalPriceEur;
    }

    public String providerName() { return providerName; }
    public int totalPriceEur() { return totalPriceEur; }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (!(o instanceof FlightProposal)) return false;
        FlightProposal that = (FlightProposal) o;
        return totalPriceEur == that.totalPriceEur
                && Objects.equals(providerName, that.providerName);
    }

    @Override
    public int hashCode() {
        return Objects.hash(providerName, totalPriceEur);
    }

    @Override
    public String toString() {
        return "FlightProposal[providerName=" + providerName
                + ", totalPriceEur=" + totalPriceEur + "]";
    }
}