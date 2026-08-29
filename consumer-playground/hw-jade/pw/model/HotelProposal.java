package pw.model;

import java.io.Serializable;
import java.util.Objects;

public final class HotelProposal implements Serializable {

    private static final long serialVersionUID = 1L;

    private final String providerName;
    private final int priceEur;

    public HotelProposal(String providerName, int priceEur) {
        this.providerName = providerName;
        this.priceEur = priceEur;
    }

    public String providerName() { return providerName; }
    public int priceEur() { return priceEur; }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (!(o instanceof HotelProposal)) return false;
        HotelProposal that = (HotelProposal) o;
        return priceEur == that.priceEur
                && Objects.equals(providerName, that.providerName);
    }

    @Override
    public int hashCode() {
        return Objects.hash(providerName, priceEur);
    }

    @Override
    public String toString() {
        return "HotelProposal[providerName=" + providerName
                + ", priceEur=" + priceEur + "]";
    }
}