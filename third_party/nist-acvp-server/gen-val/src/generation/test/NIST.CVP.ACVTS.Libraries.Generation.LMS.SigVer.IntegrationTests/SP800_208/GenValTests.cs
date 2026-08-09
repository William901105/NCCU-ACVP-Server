using NIST.CVP.ACVTS.Libraries.Common;
using NIST.CVP.ACVTS.Libraries.Crypto.Common.Asymmetric.LMS.Native.Enums;
using NIST.CVP.ACVTS.Libraries.Generation.LMS.SP800_208.Shared;
using NIST.CVP.ACVTS.Libraries.Generation.LMS.SP800_208.SigVer;
using NIST.CVP.ACVTS.Libraries.Generation.Tests;
using NIST.CVP.ACVTS.Libraries.Math.Domain;
using NIST.CVP.ACVTS.Tests.Core.TestCategoryAttributes;
using NUnit.Framework;

namespace NIST.CVP.ACVTS.Libraries.Generation.LMS.SigVer.IntegrationTests.SP800_208;

[TestFixture, LongRunningIntegrationTest]
public class GenValTests : GenValTestsSingleRunnerBase
{
    public override AlgoMode AlgoMode => AlgoMode.LMS_SigVer_SP800_208;
    public override string Algorithm => "LMS";
    public override string Mode => "sigVer";
    public override string Revision => "SP800-208";
    public override IRegisterInjections RegistrationsGenVal => new RegisterInjections();
    
    protected override void ModifyTestCaseToFail(dynamic testCase)
    {
        if (testCase.testPassed != null)
        {
            testCase.testPassed = !(bool)testCase.testPassed;
        }
    }

    protected override string GetTestFileFewTestCases(string folderName)
    {
        var p = new Parameters
        {
            Algorithm = Algorithm,
            Mode = Mode,
            Revision = Revision,
            Capabilities = new GeneralCapabilities
            {
                LmsModes = [LmsMode.LMS_SHA256_M24_H5],
                LmOtsModes = [LmOtsMode.LMOTS_SHA256_N24_W1]
            },
            MessageLength = new MathDomain().AddSegment(new ValueDomainSegment(1024))
        };
        
        return CreateRegistration(folderName, p);
    }

    protected override string GetTestFileLotsOfTestCases(string folderName)
    {
        var p = new Parameters
        {
            Algorithm = Algorithm,
            Mode = Mode,
            Revision = Revision,
            Capabilities = new GeneralCapabilities
            {
                LmsModes = [LmsMode.LMS_SHA256_M24_H5, LmsMode.LMS_SHA256_M24_H10],
                LmOtsModes = [LmOtsMode.LMOTS_SHA256_N24_W1, LmOtsMode.LMOTS_SHA256_N24_W2]
            },
            MessageLength = new MathDomain().AddSegment(new RangeDomainSegment(null, ParameterValidator.MIN_MESSAGE_LENGTH,  ParameterValidator.MAX_MESSAGE_LENGTH, 8))
        };
        
        return CreateRegistration(folderName, p);
    }
}
