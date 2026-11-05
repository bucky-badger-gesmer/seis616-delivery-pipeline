# Software Delivery Pipeline

SEIS 616 CloudFormation homework. `pipeline.yaml` creates a delivery pipeline with GitHub, CodePipeline, and CodeBuild, plus a **manual review stage**. When code is pushed to `main`, the pipeline pauses and emails the maintainer. It builds only after the change is approved.

The pipeline builds the small Python app in this repo (`rectangle/`): it runs the pytest tests and packages the app as one runnable file, `rectangle.pyz`.

```
git push ──► Source ──► Approval (email, waits) ──► Build (pytest + package)
```

Each step below can be done in the **AWS console** (in your browser) or with the **AWS CLI** (in a terminal). Pick one.

## 1. Run the template

You need a GitHub connection in us-east-1 with status **Available**. Find it in the console under **Developer Tools → Settings → Connections**.

### Fill in the values

| Value             | Where to find it                                                                                     |
| ----------------- | ---------------------------------------------------------------------------------------------------- |
| `ConnectionArn`   | The ARN of your GitHub connection, from the Connections page above.                                  |
| `RepositoryId`    | The GitHub repo to build, as `owner/name`. Default: `bucky-badger-gesmer/seis616-delivery-pipeline`. |
| `BranchName`      | The branch to watch. Default: `main`.                                                                |
| `MaintainerEmail` | The email address that gets review requests.                                                         |

### Option A: AWS console

1. Sign in to the AWS console and set the region to **US East (N. Virginia) us-east-1** in the top right.
2. Open **CloudFormation** and click **Create stack → With new resources (standard)**.
3. Choose **Upload a template file**, select `pipeline.yaml`, and click **Next**.
4. Enter `seis616-pipeline` as the stack name, fill in the values above, and click **Next**.
5. On the next page, leave the settings as they are. At the bottom, check **I acknowledge that AWS CloudFormation might create IAM resources** and click **Next**.
6. Review the summary and click **Submit**. Wait until the stack shows **CREATE_COMPLETE** (about 1 minute).

### Option B: AWS CLI

Run this from this repo's folder so `file://pipeline.yaml` can find the template.

```bash
aws cloudformation create-stack \
  --region us-east-1 \
  --stack-name seis616-pipeline \
  --template-body file://pipeline.yaml \
  --capabilities CAPABILITY_IAM \
  --parameters \
    ParameterKey=ConnectionArn,ParameterValue=<connection-arn> \
    ParameterKey=MaintainerEmail,ParameterValue=<your-email>
aws cloudformation wait stack-create-complete --region us-east-1 --stack-name seis616-pipeline
```

`CAPABILITY_IAM` (the checkbox in step 5 of the console option) is needed because the template creates IAM roles for CodePipeline and CodeBuild.

### Confirm the email subscription

Open the **AWS Notification - Subscription Confirmation** email and click **Confirm subscription**. Review emails aren't delivered until you do.

## 2. Verify it worked

1. Push a commit to `main`. The pipeline starts and stops at the **Approval** stage. (Pushes that change only `README.md` or `docs/` don't start the pipeline.)
2. The maintainer gets an **APPROVAL NEEDED** email with the commit ID, the commit message, and a link to the commit on GitHub.
3. Approve or reject the change:
   - **Console:** Open **CodePipeline → seis616-pipeline**, click **Review** on the Approval stage, then **Approve** or **Reject**.
   - **CLI:**

     ```bash
     TOKEN=$(aws codepipeline get-pipeline-state --region us-east-1 --name seis616-pipeline \
       --query "stageStates[?stageName=='Approval'].actionStates[0].latestExecution.token" --output text)
     aws codepipeline put-approval-result --region us-east-1 --pipeline-name seis616-pipeline \
       --stage-name Approval --action-name MaintainerReview --token $TOKEN \
       --result summary='Looks good',status=Approved
     ```

4. **Approved:** the Build stage runs the tests and saves `rectangle.pyz` to the artifact bucket. **Rejected:** the run stops as **Failed** and nothing is built.

## 3. Tear it down

The stack can't delete its artifact bucket while files are in it, and CodeBuild creates a log group and a test report group that the stack doesn't delete. Remove all of them:

```bash
BUCKET=$(aws cloudformation describe-stacks --region us-east-1 --stack-name seis616-pipeline \
  --query "Stacks[0].Outputs[?OutputKey=='ArtifactBucketName'].OutputValue" --output text)
aws s3 rm s3://$BUCKET --recursive
aws cloudformation delete-stack --region us-east-1 --stack-name seis616-pipeline
aws cloudformation wait stack-delete-complete --region us-east-1 --stack-name seis616-pipeline
aws codebuild delete-report-group --region us-east-1 --delete-reports \
  --arn arn:aws:codebuild:us-east-1:<account-id>:report-group/seis616-pipeline-build-pytest-reports
aws logs delete-log-group --region us-east-1 --log-group-name /aws/codebuild/seis616-pipeline-build
```

If `aws sns list-subscriptions` still shows the email subscription afterward, remove it with `aws sns unsubscribe`.

## How I verified it

I launched `pipeline.yaml` as `seis616-pipeline` in us-east-1 with the CLI.

- **Stack created:** The stack reached **CREATE_COMPLETE** on the first try, with all six resources (artifact bucket, SNS topic, two IAM roles, build project, pipeline).
- **Rejected change:** Creating the pipeline started a run on commit `192d80e`. It paused at Approval (Source **Succeeded**, Approval **InProgress**, Build not started). I rejected it. The run ended as **Failed**, and `aws codebuild list-builds-for-project` returned no builds.
- **Approved change:** I pushed commit `6fbc395` (adds `diagonal()` and its test). GitHub started a new run, which paused at Approval, and the **APPROVAL NEEDED** email arrived (SNS: 2 published, 2 delivered, 0 failed). I approved it in the console. The pipeline resumed and the build succeeded: Python 3.12.15, `5 passed`, and the smoke run printed `area=12.0 perimeter=14.0 diagonal=5.0`. I downloaded `rectangle.pyz` from the artifact bucket and it printed the same line locally.
- **Docs-only push:** Pushing a change to only `README.md` (commit `6db9308`) did not start a run.
- **Teardown:** I ran the commands above. The stack shows **DELETE_COMPLETE**, and a sweep of the account found no pipelines, build projects, report groups, log groups, SNS topics or subscriptions, or IAM roles left from this project.
