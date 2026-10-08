@AbapCatalog.viewEnhancementCategory: [#NONE]
@AccessControl.authorizationCheck: #NOT_REQUIRED
@EndUserText.label: 'P2P extraction: purchase order item'
@Metadata.ignorePropagatedAnnotations: true
@ObjectModel.usageType: { serviceQuality: #D, sizeCategory: #XL, dataClass: #TRANSACTIONAL }
@Analytics.dataCategory: #FACT
@Analytics.dataExtraction.enabled: true
@Analytics.dataExtraction.delta.changeDataCapture.automatic: true
define view entity ZX_P2P_EKPO
  as select from ekpo
{
  key ebeln,
  key ebelp,
      loekz,
      txz01,
      matnr,
      werks,
      lgort,
      matkl,
      @Semantics.quantity.unitOfMeasure: 'meins'
      menge,
      meins,
      // NETPR/NETWR reference the currency key on EKKO-WAERS, which is not in this
      // table-grain view: extract them as plain decimals and pair them with the header
      // currency in the lakehouse.
      cast( netpr as abap.dec( 11, 2 ) ) as netpr,
      peinh,
      cast( netwr as abap.dec( 13, 2 ) ) as netwr,
      mwskz,
      knttp,
      elikz,
      erekz,
      wepos,
      repos,
      webre,
      banfn,
      bnfpo,
      aedat
}
where
  bstyp = 'F'
